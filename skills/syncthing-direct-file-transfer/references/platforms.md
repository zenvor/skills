# 设备操作经验

## Windows 进程与防火墙

使用附带脚本时先检查 `py -3 --version`、`curl.exe --version` 与系统 Windows PowerShell/CIM。将[命令流程](commands.md)中的 `python3` 换成 `py -3`，路径换成本机带引号的绝对路径。例如从技能目录执行：

```powershell
py -3 .\scripts\launch.py --root "$env:LOCALAPPDATA\SyncthingDirect\A" --sender
# 另开终端检查本次实例。
py -3 .\scripts\control.py --root "$env:LOCALAPPDATA\SyncthingDirect\A" status
```

已有个人 Syncthing 保持原样，临时传输另选配置目录和空闲端口。启动器用独占文件句柄保护配置，子进程也继承锁；强制结束父进程可能留下子进程，不要通过重写配置处理残留。

前台优先 Control+C；后台用 `control.py --root ... stop`。它通过 PID、创建时间和命令只清理本次父子进程，API 离线也可使用；身份查询失败时不猜测。不要使用 `taskkill /IM syncthing.exe` 或停止所有 Python 进程。

防火墙按以下顺序核对：

1. 确认实际 `syncthing.exe` 路径、监听端口，以及承载流量网卡的 Public/Private 配置文件。TUN 与物理网卡可能不同。
2. 检查匹配程序的显式入站阻止规则。显式阻止优先于允许，仅新增允许规则可能无效。
3. 需要修正时只调整已核实且在授权范围内的程序规则，按活动配置文件放行实际同步 TCP/UDP 端口。附带脚本默认均为 22000；GUI 8385 只绑定回环，不开放到外网。

不通过关闭整个防火墙或改变网络类别绕过问题；本机放行不代表已解决上游 NAT。代理接管另按[代理分流](proxy-routing.md)判断。

## Android 客户端接收

使用用户已有的客户端。配对设备与共享目录分别处理，不因添加设备自动共享已有目录或整个 Downloads。

1. 核对设备 ID、目录 ID、共享范围及收发方向。接受发送端提供的目录，或用相同目录 ID 手动添加，只选择本次发送设备。
2. 优先用原生文件夹选择器，在内部共享存储创建独立接收目录。保存前核对完整绝对路径，例如 `/storage/emulated/0/Transfer-Inbox`，不要复用桌面路径。
3. 单向接收使用 `receiveonly`。遇到只读或建目录失败，先检查是否误指根目录、路径前多了文字，以及位置是否可写。确认真实权限限制后，再按客户端、Android 版本和用户授权授予所需权限。
4. 需要重建错误目录配置时，先确认它确属本次且为空，仅移除错误配置，不删除已有文件。已含数据时先确认保留与迁移方式。
5. 检查实际接收字节增长、无路径错误及当前 TCP/QUIC 连接。`isLocal=true` 或下载开始都不代表文件已验收，最终按源清单核对。

这里使用客户端原生界面或其适用接口，不能把专用配置的 `control.py` 命令直接套到手机上。

## 官方参考

- [Syncthing 防火墙](https://docs.syncthing.net/users/firewall.html)
- [Windows 句柄继承](https://learn.microsoft.com/en-us/windows/win32/procthread/inheritance)
