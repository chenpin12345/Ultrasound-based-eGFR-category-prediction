"""Receiver listen address on B: discovery, manual entry and validation.

Only the image receiver listens on the LAN; the main application stays loopback.
IPv6 is reported but not supported in this version (socket, URL, certificate and
sender would all need to change together).
"""
from __future__ import annotations

import ipaddress
import socket

from ..core.errors import AppError

KIND_ORDER={'private':0,'link_local':1,'loopback':2,'other':3,'ipv6':4}
NOTES={'loopback':'僅限同一台電腦測試；A 電腦無法連到此位址。',
       'link_local':'169.254 自動位址：網卡未取得 DHCP 位址時產生，只適用兩台電腦直接連線且同為 169.254 網段。',
       'private':'區域網路位址。',
       'other':'非私有網段位址；A 傳送工具不接受，避免接收程序暴露到外部網路。',
       'ipv6':'本版不支援 IPv6，請使用 IPv4 位址。'}


def classify(address):
    ip=ipaddress.ip_address(address)
    if ip.version==6: return 'ipv6'
    if ip.is_loopback: return 'loopback'
    if ip.is_link_local: return 'link_local'
    if ip.is_private: return 'private'
    return 'other'


def interfaces():
    """Every local address with its interface name and link state."""
    result=[]
    try:
        import psutil
        stats=psutil.net_if_stats()
        for name,entries in psutil.net_if_addrs().items():
            up=stats[name].isup if name in stats else None
            for entry in entries:
                if entry.family not in (socket.AF_INET,socket.AF_INET6): continue
                address=entry.address.split('%')[0]
                kind=classify(address)
                result.append({'interface':name,'address':address,'family':4 if entry.family==socket.AF_INET else 6,
                               'is_up':up,'kind':kind,'supported':kind in ('private','link_local','loopback'),'note':NOTES[kind]})
    except ImportError:
        for address in {'127.0.0.1',*socket.gethostbyname_ex(socket.gethostname())[2]}:
            kind=classify(address)
            result.append({'interface':'（未知）','address':address,'family':4,'is_up':None,'kind':kind,
                           'supported':kind in ('private','link_local','loopback'),'note':NOTES[kind]})
    return sorted(result,key=lambda r:(r['is_up'] is False,KIND_ORDER[r['kind']],r['interface'],r['address']))


def recommended(items):
    """Suggest an address only when the choice is unambiguous."""
    candidates=[i for i in items if i['kind']=='private' and i['is_up'] is not False]
    return candidates[0]['address'] if len(candidates)==1 else None


def validate(host,port=None):
    """Raise a specific, user-readable error unless B can listen on host:port."""
    try: ip=ipaddress.ip_address(str(host).strip())
    except ValueError:
        raise AppError(422,'BIND_ADDRESS_INVALID','位址格式錯誤；請輸入 B 電腦的 IPv4 位址，例如 192.168.1.20。') from None
    if ip.version==6: raise AppError(422,'BIND_IPV6_UNSUPPORTED','本版接收程序不支援 IPv6，請使用 B 的 IPv4 位址。')
    if ip.is_unspecified: raise AppError(422,'BIND_WILDCARD','不可使用 0.0.0.0：會讓接收程序在所有網卡上開放，請指定單一網卡位址。')
    if not (ip.is_private or ip.is_loopback):
        raise AppError(422,'BIND_NOT_PRIVATE','此位址不是區域網路位址；接收程序只能在區域網路或本機位址上開放。')
    if port is not None and not 1024<=port<=65535:
        raise AppError(422,'PORT_RANGE','連接埠須介於 1024 至 65535；留空則由系統自動配置。')
    match=[i for i in interfaces() if i['address']==str(ip)]
    if not match:
        raise AppError(422,'BIND_NOT_LOCAL','此位址不屬於 B（本機）的任何網路介面。它可能是 A 電腦、其他裝置或尚未設定的 IP；請輸入 B 自己的位址，或改用自動偵測。')
    if all(i['is_up'] is False for i in match):
        raise AppError(409,'BIND_INTERFACE_DOWN',f'網卡「{match[0]["interface"]}」目前未連線，請確認網路線或 Wi-Fi 後重試。')
    return {'host':str(ip),'port':port,'interface':match[0]['interface'],'kind':match[0]['kind']}


BIND_ERRORS={'PORT_IN_USE':(409,'連接埠已被其他程式使用；請改用其他連接埠，或留空由系統自動配置。'),
             'ADDRESS_NOT_AVAILABLE':(409,'此位址目前無法綁定，可能網卡剛剛變更或中斷；請重新偵測位址。'),
             'BIND_DENIED':(409,'系統拒絕綁定此連接埠（權限或保留埠）；請改用其他連接埠或留空自動配置。'),
             'RECEIVER_START_FAILED':(503,'接收程序無法啟動，請查看作業監控後重試。')}


def bind_error(code):
    status,message=BIND_ERRORS.get(code,BIND_ERRORS['RECEIVER_START_FAILED'])
    return AppError(status,code if code in BIND_ERRORS else 'RECEIVER_START_FAILED',message)
