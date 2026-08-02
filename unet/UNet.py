"""UNet模型與訓練定義"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.data as data
from torchvision import transforms
from torchvision.transforms import functional as TF
from PIL import Image
import numpy as np
import glob
import os
from torch.utils.data import get_worker_info
import copy
import time
import random
from typing import Dict

# 在頂層定義 SegmentationDataset
class SegmentationDataset(torch.utils.data.Dataset):
    _print_once = False
    def __init__(self, img_paths, mask_paths, transform=None, mask_transform=None):
        # 支援多種圖片格式
        self.img_paths = []
        for ext in ['.png', '.jpg', '.jpeg', '.bmp']:
            self.img_paths.extend(glob.glob(os.path.join(img_paths, f'*{ext}')))
        self.img_paths = sorted(self.img_paths)
        
        # 檢查對應的遮罩檔案
        self.mask_paths = []
        for img_path in self.img_paths:
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            mask_path = os.path.join(mask_paths, f"{base_name}.png")  # 遮罩都是PNG
            if os.path.exists(mask_path):
                self.mask_paths.append(mask_path)
            else:
                print(f"警告: 找不到遮罩檔案 {mask_path}")
        
        # 過濾掉沒有對應遮罩的圖片
        valid_pairs = list(zip(self.img_paths, self.mask_paths))
        if len(valid_pairs) == 0:
            raise ValueError(f"在 {img_paths} 中找不到有效的圖片-遮罩配對")
            
        self.img_paths, self.mask_paths = zip(*valid_pairs)
        self.transform = transform
        
        if not SegmentationDataset._print_once and get_worker_info() is None:
            print(f"載入了 {len(self.img_paths)} 對圖片-遮罩配對")
            SegmentationDataset._print_once = True

    def __len__(self):
        return len(self.img_paths)

    def __getitem__(self, idx):
        img = Image.open(self.img_paths[idx]).convert('RGB')
        mask = Image.open(self.mask_paths[idx]).convert('L')

        if self.transform:
            img, mask = self.transform(img, mask)

        # 將 mask 轉成 LongTensor 並確保值合法
        mask = torch.from_numpy(np.array(mask)).long()
        mask = (mask > 0).long()  # 只要大於0視為1

        mask = mask.squeeze()
        return img, mask


def transform_img_mask(img, mask): 
    """建立圖片與遮罩的共同轉換，確保隨機增強一致"""
    # Resize
    img = TF.resize(img, (512, 512))
    mask = TF.resize(mask, (512, 512), interpolation=transforms.InterpolationMode.NEAREST)
    
    if random.random() > 0.5:
        angle = random.uniform(-7, 7)
        img = TF.rotate(img, angle, interpolation=transforms.InterpolationMode.BILINEAR)
        mask = TF.rotate(mask, angle, interpolation=transforms.InterpolationMode.NEAREST)
    
    # 隨機翻轉
    if random.random() > 0.5:
        img = TF.hflip(img); mask = TF.hflip(mask)

    # 隨機亮度/對比度
    if random.random() > 0.5:
        img = TF.adjust_brightness(img, 0.9 + 0.2 * random.random())
    if random.random() > 0.5:
        img = TF.adjust_contrast(img, 0.9 + 0.2 * random.random())
    
    # To Tensor
    img = TF.to_tensor(img)
    mask = torch.as_tensor(np.array(mask), dtype=torch.long)

    # Normalize (只對 image)
    img = TF.normalize(img, mean=[0.485, 0.456, 0.406], 
                            std=[0.229, 0.224, 0.225])

    return img, mask

def eval_transform(img, mask):
    """評估階段的轉換，不含隨機增強"""
    img = TF.resize(img, (512, 512))
    mask = TF.resize(mask, (512, 512), interpolation=transforms.InterpolationMode.NEAREST)
    img  = TF.to_tensor(img)
    img  = TF.normalize(img, mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    mask = torch.as_tensor(np.array(mask), dtype=torch.long)

    return img, mask

def get_dataloader(train_images, train_masks, val_images, val_masks, test_images, test_masks, batch_size):
    """建立資料加載器"""
    train_dataset = SegmentationDataset(train_images, train_masks, transform=transform_img_mask)
    val_dataset   = SegmentationDataset(val_images, val_masks, transform=eval_transform)
    test_dataset  = SegmentationDataset(test_images, test_masks, transform=eval_transform)

    return {
        'train': data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=3, pin_memory=True, prefetch_factor=2),
        'val':   data.DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=3, pin_memory=True),
        'test':  data.DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=3, pin_memory=True)
    }

class DoubleConv(nn.Sequential):
    """雙重卷積模組: (conv -> BN -> ReLU) * 2"""
    def __init__(self, in_channels, out_channels, mid_channels=None):
        if mid_channels is None:
            mid_channels = out_channels
        super(DoubleConv, self).__init__(
            nn.Conv2d(in_channels, mid_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(mid_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(mid_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )

class Down(nn.Sequential):
    """下採樣: maxpool -> double conv"""
    def __init__(self, in_channels, out_channels):
        super(Down, self).__init__(
            nn.MaxPool2d(2, stride=2),
            DoubleConv(in_channels, out_channels)
        )

class Up(nn.Module):
    """上採樣: transpose conv -> concat -> double conv"""
    def __init__(self, in_channels, out_channels, bilinear=True):
        super(Up, self).__init__()
        if bilinear:
            self.up = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.conv = DoubleConv(in_channels, out_channels, in_channels // 2)
        else:
            self.up = nn.ConvTranspose2d(in_channels, in_channels // 2, kernel_size=2, stride=2)
            self.conv = DoubleConv(in_channels, out_channels)

    def forward(self, x1: torch.Tensor, x2: torch.Tensor) -> torch.Tensor:
        x1 = self.up(x1)
        
        # 處理尺寸不匹配的情況
        diff_y = x2.size()[2] - x1.size()[2]
        diff_x = x2.size()[3] - x1.size()[3]
        
        # padding_left, padding_right, padding_top, padding_bottom
        x1 = F.pad(x1, [diff_x // 2, diff_x - diff_x // 2,
                        diff_y // 2, diff_y - diff_y // 2])
        
        # 跳躍連接: 拼接來自編碼器的特徵
        x = torch.cat([x2, x1], dim=1)
        x = self.conv(x)
        return x

class OutConv(nn.Sequential):
    """輸出卷積層"""
    def __init__(self, in_channels, num_classes):
        super(OutConv, self).__init__(
            nn.Conv2d(in_channels, num_classes, kernel_size=1)
        )

class UNet(nn.Module):
    """標準 U-Net 架構"""
    def __init__(self,
                 in_channels: int = 3,
                 num_classes: int = 2,
                 bilinear: bool = True,
                 base_c: int = 32):
        super(UNet, self).__init__()
        self.in_channels = in_channels
        self.num_classes = num_classes
        self.bilinear = bilinear

        # 編碼器 (Encoder/Contracting Path)
        self.in_conv = DoubleConv(in_channels, base_c)
        self.down1 = Down(base_c, base_c * 2)
        self.down2 = Down(base_c * 2, base_c * 4)
        self.down3 = Down(base_c * 4, base_c * 8)
        factor = 2 if bilinear else 1
        self.down4 = Down(base_c * 8, base_c * 16 // factor)
        
        # 解碼器 (Decoder/Expansive Path)
        self.up1 = Up(base_c * 16, base_c * 8 // factor, bilinear)
        self.up2 = Up(base_c * 8, base_c * 4 // factor, bilinear)
        self.up3 = Up(base_c * 4, base_c * 2 // factor, bilinear)
        self.up4 = Up(base_c * 2, base_c, bilinear)
        self.out_conv = OutConv(base_c, num_classes)
        
        self._initialize_weights()

    def _initialize_weights(self):
        """權重初始化"""
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.ConvTranspose2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')

    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        orig_h, orig_w = x.size(2), x.size(3)
        # 先 downsample 一次到 1/2（512->256）
        x = F.interpolate(x, scale_factor=0.5, mode='bilinear', align_corners=True)
        # 編碼路徑
        x1 = self.in_conv(x)      # [B, base_c, H, W]
        x2 = self.down1(x1)       # [B, base_c*2, H/2, W/2]
        x3 = self.down2(x2)       # [B, base_c*4, H/4, W/4]
        x4 = self.down3(x3)       # [B, base_c*8, H/8, W/8]
        x5 = self.down4(x4)       # [B, base_c*16, H/16, W/16]
        
        # 解碼路徑 (含跳躍連接)
        x = self.up1(x5, x4)      # [B, base_c*8, H/8, W/8]
        x = self.up2(x, x3)       # [B, base_c*4, H/4, W/4]
        x = self.up3(x, x2)       # [B, base_c*2, H/2, W/2]
        x = self.up4(x, x1)       # [B, base_c, H, W]
        logits = self.out_conv(x) # [B, num_classes, H, W]
        
        # 將 logits 上採樣回原始尺寸（512）
        logits = F.interpolate(logits, size=(orig_h, orig_w), mode='bilinear', align_corners=True)
        return {"out": logits}

def train_model(model, train_loader, criterion, optimizer, num_epochs,
                update_callback=None, val_loader=None, patience=5,
                device='cuda'):
    
    best_dice = 0.0  # 改为跟踪最佳 Dice Score
    start_time = time.time()
    scaler = torch.amp.GradScaler(enabled=(device=="cuda"))
    best_epoch = 0
    epochs_no_improve = 0
    best_model_state = None
    model.to(device)

    use_autocast = (device == "cuda" and torch.cuda.is_available())

    for epoch in range(1, num_epochs + 1):
        # ====== 訓練階段 ======
        model.train()
        running_loss = 0.0
        valid_batches = 0
        
        for batch_idx, (images, masks) in enumerate(train_loader, 1):
            images, masks = images.to(device), masks.to(device)
            optimizer.zero_grad()
            
            if use_autocast:
                with torch.amp.autocast(device_type="cuda"):
                    outputs = model(images)["out"]  # 修改這裡以適應字典輸出
                    loss = criterion(outputs, masks)
            else:
                outputs = model(images)["out"]  # 修改這裡以適應字典輸出
                loss = criterion(outputs, masks)
            
            # 檢查 loss 是否為 nan
            if torch.isnan(loss):
                print(f"警告: 第 {epoch} 回合第 {batch_idx} 批次 loss 為 nan，跳過此 batch")
                continue
                
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            running_loss += loss.item()
            valid_batches += 1

            # Batch callback
            if update_callback:
                update_callback(epoch, num_epochs, batch_idx, len(train_loader))

        epoch_train_loss = running_loss / valid_batches if valid_batches > 0 else float('nan')

        # ====== 驗證階段 ======
        val_loss = None
        val_acc = None
        val_dice = None
        epoch_iou = 0.0

        if val_loader is not None:
            model.eval()
            val_ious = []
            val_running_loss = 0.0
            val_batches = 0
            correct = 0
            total = 0
            dice_scores = []

            with torch.no_grad():
                for images, masks in val_loader:
                    images, masks = images.to(device), masks.to(device)
                    outputs = model(images)["out"]  # 修改這裡以適應字典輸出
                    loss = criterion(outputs, masks)
                    
                    if torch.isnan(loss):
                        print(f"警告: 驗證 loss 為 nan，跳過此 batch")
                        continue
                        
                    val_running_loss += loss.item()
                    val_batches += 1
                    preds = outputs.argmax(1)

                    # Accuracy
                    correct += (preds == masks).sum().item()
                    total += masks.numel()

                    # Dice Score (foreground=1)
                    intersection = ((preds == 1) & (masks == 1)).sum().item()
                    pred_sum = (preds == 1).sum().item()
                    true_sum = (masks == 1).sum().item()
                    dice = (2.0 * intersection) / (pred_sum + true_sum) if (pred_sum + true_sum) > 0 else 0
                    dice_scores.append(dice)

                    # IoU
                    for pred, target in zip(preds, masks):
                        inter = ((pred == 1) & (target == 1)).sum().item()
                        uni = ((pred == 1) | (target == 1)).sum().item()
                        if uni > 0:
                            val_ious.append(inter / uni)

            val_loss = val_running_loss / val_batches if val_batches > 0 else float('nan')
            val_acc = correct / total if total > 0 else None
            val_dice = np.mean(dice_scores) if dice_scores else 0.0  # 确保有默认值
            epoch_iou = np.mean(val_ious) if val_ious else 0

            print(f'\033[96mEpoch\033[0m {epoch:>2}: '
                  f'\033[38;5;180mTrain Loss\033[0m={epoch_train_loss:.4f}, '
                  f'\033[38;5;180mVal Loss\033[0m={val_loss:.4f}, '
                  f'\033[38;5;180mVal IoU\033[0m={epoch_iou:.4f}, '
                  f'\033[38;5;180mVal Dice\033[0m={val_dice:.4f}, '
                  f'\033[38;5;180mVal Acc\033[0m={val_acc*100:.2f}%,')

            # Early Stopping - 改为使用 Dice Score
            if val_dice > best_dice:
                best_dice = val_dice
                best_epoch = epoch
                epochs_no_improve = 0
                best_model_state = copy.deepcopy(model.state_dict())
            else:
                epochs_no_improve += 1

            if epochs_no_improve >= patience:
                print(f"Early stopping at epoch {epoch:>2}. "
                      f"Best Dice Score: {best_dice:.4f} at epoch {best_epoch}")
                if best_model_state is not None:
                    model.load_state_dict(best_model_state)
                break

        # Epoch callback: 只更新 val_loss/acc/dice 曲線
        if update_callback:
            update_callback(epoch, num_epochs, len(train_loader), len(train_loader),
                            train_loss=epoch_train_loss, val_loss=val_loss, val_acc=val_acc, val_dice=val_dice)

    total_time = time.time() - start_time
    return model, best_dice, int(total_time // 60), int(total_time % 60)


def save_model(model, path):
    """儲存模型"""
    torch.save(model.state_dict(), path)

def load_model(model, path):
    """載入模型"""
    model.load_state_dict(torch.load(path))
    return model