"""模型架構（改寫自訓練網站 ml/segmentation.py 的 build_unet，並修正分類頭）。

初始化方式（D2）：'random'（預設）或 'imagenet'（必須先下載權重，消融實驗比較兩者）。
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.models as tvm

from . import pretrained

HEADS = ('binary', 'ce', 'coral', 'corn', 'sord')


def _resnet(arch: str, init: str) -> nn.Module:
    model = getattr(tvm, arch)(weights=None)
    if init == 'imagenet':
        model.load_state_dict(pretrained.torchvision_state(f'{arch}-imagenet'))
    return model


def _block(cin: int, cout: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
        nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
    )


class UNet(nn.Module):
    """經典 UNet（隨機初始化）。"""

    def __init__(self, num_classes: int = 5, base: int = 32):
        super().__init__()
        chs = [base, base * 2, base * 4, base * 8, base * 16]
        self.downs = nn.ModuleList([_block(1 if i == 0 else chs[i - 1], c) for i, c in enumerate(chs)])
        self.ups = nn.ModuleList([nn.ConvTranspose2d(chs[i], chs[i - 1], 2, stride=2) for i in range(4, 0, -1)])
        self.decs = nn.ModuleList([_block(chs[i - 1] * 2, chs[i - 1]) for i in range(4, 0, -1)])
        self.head = nn.Conv2d(base, num_classes, 1)

    def forward(self, x):
        skips = []
        for i, down in enumerate(self.downs):
            x = down(x if i == 0 else F.max_pool2d(x, 2))
            skips.append(x)
        x = skips.pop()
        for up, dec in zip(self.ups, self.decs):
            x = up(x)
            x = dec(torch.cat([x, skips.pop()], 1))
        return self.head(x)


class ResNetUNet(nn.Module):
    """ResNet-34 編碼器的 UNet（可用 ImageNet 初始化）。輸入灰階，複製成 3 通道。"""

    def __init__(self, num_classes: int = 5, init: str = 'random'):
        super().__init__()
        r = _resnet('resnet34', init)
        self.stem = nn.Sequential(r.conv1, r.bn1, r.relu)  # 1/2, 64
        self.pool = r.maxpool
        self.enc = nn.ModuleList([r.layer1, r.layer2, r.layer3, r.layer4])  # 1/4 64, 1/8 128, 1/16 256, 1/32 512
        skip_ch = [256, 128, 64, 64]
        self.ups = nn.ModuleList()
        self.decs = nn.ModuleList()
        cin = 512
        for sc, cout in zip(skip_ch, [256, 128, 64, 64]):
            self.ups.append(nn.ConvTranspose2d(cin, cout, 2, stride=2))
            self.decs.append(_block(cout + sc, cout))
            cin = cout
        self.final_up = nn.ConvTranspose2d(64, 32, 2, stride=2)
        self.final = nn.Sequential(_block(32, 32), nn.Conv2d(32, num_classes, 1))

    def forward(self, x):
        x = x.repeat(1, 3, 1, 1)
        s0 = self.stem(x)
        x = self.pool(s0)
        feats = []
        for layer in self.enc:
            x = layer(x)
            feats.append(x)
        skips = [feats[2], feats[1], feats[0], s0]
        x = feats[3]
        for up, dec, skip in zip(self.ups, self.decs, skips):
            x = up(x)
            x = dec(torch.cat([x, skip], 1))
        return self.final(self.final_up(x))


def build_segmentation(arch: str, init: str, num_classes: int = 5) -> nn.Module:
    if arch == 'unet':
        if init != 'random':
            raise ValueError('經典 UNet 沒有 ImageNet 權重，請改用 resnet34-unet。')
        return UNet(num_classes)
    if arch == 'resnet34-unet':
        return ResNetUNet(num_classes, init)
    raise ValueError(f'不支援的分割架構：{arch}')


class OrdinalCoral(nn.Module):
    """正確版 CORAL：所有門檻共用一組權重，只有偏差不同（舊程式每個門檻各自一組權重，不具秩一致性）。"""

    def __init__(self, in_features: int, num_classes: int):
        super().__init__()
        self.fc = nn.Linear(in_features, 1, bias=False)
        self.biases = nn.Parameter(torch.linspace(1, -1, num_classes - 1))

    def forward(self, x):
        return self.fc(x) + self.biases


class Classifier(nn.Module):
    """ResNet 影像骨幹；可再接表格特徵（腎長、灰階比等）做 late fusion。"""

    def __init__(self, arch: str, init: str, head: str, num_classes: int, n_features: int = 0, in_channels: int = 1):
        super().__init__()
        if head not in HEADS:
            raise ValueError(f'不支援的輸出頭：{head}')
        r = _resnet(arch, init)
        self.in_channels = in_channels
        if in_channels != 1:
            # ④ 影像＋遮罩通道：影像通道沿用原本的權重（RGB 加總，等於把灰階複製成 3 通道），遮罩通道從 0 開始，
            # 所以訓練開始時和只用影像的模型完全相同（不額外消耗亂數），比較最乾淨
            w = r.conv1.weight.detach()
            with torch.random.fork_rng(devices=[]):  # 建立卷積層會消耗亂數，還原後輸出層的初始值才和 ① 相同
                conv = nn.Conv2d(in_channels, w.shape[0], 7, 2, 3, bias=False)
            with torch.no_grad():
                conv.weight.zero_()
                conv.weight[:, :1] = w.sum(1, keepdim=True)
            r.conv1 = conv
        dim = r.fc.in_features
        r.fc = nn.Identity()
        self.backbone = r
        self.n_features = n_features
        if n_features:
            self.tab = nn.Sequential(nn.Linear(n_features, 32), nn.ReLU(inplace=True))
            dim += 32
        self.dropout = nn.Dropout(0.2)
        out = {'binary': 1, 'ce': num_classes, 'sord': num_classes, 'corn': num_classes - 1}.get(head)
        self.head_kind = head
        self.head = OrdinalCoral(dim, num_classes) if head == 'coral' else nn.Linear(dim, out)

    def forward(self, x, features=None):
        z = self.backbone(x.repeat(1, 3, 1, 1) if self.in_channels == 1 else x)
        if self.n_features:
            z = torch.cat([z, self.tab(features)], 1)
        return self.head(self.dropout(z))


def build_classifier(arch: str, init: str, head: str, num_classes: int, n_features: int = 0, in_channels: int = 1) -> nn.Module:
    if arch not in ('resnet18', 'resnet34'):
        raise ValueError(f'不支援的分類骨幹：{arch}')
    return Classifier(arch, init, head, num_classes, n_features, in_channels)
