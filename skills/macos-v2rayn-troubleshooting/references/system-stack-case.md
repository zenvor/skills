# system 栈切换实战：2026-10-28

本记录是当次排障证据，不是当前机器状态或所有版本行为的保证。后续操作仍需读取实际配置与版本。

## 现场与操作

- 环境：macOS arm64，v2rayN 7.25.6，sing-box 1.14.4，原 TUN stack 为 gvisor；链路为 TUN → 本地 SOCKS → Xray → Hysteria2。
- 日志在 Notes/Gmail 993 及多个 HTTPS 目标上出现 `connection download closed: close tcp ... endpoint not connected`。用户确认正常使用；捕捉到的 WhatsApp 连接在关闭前已有双向数据。GitHub 同地址的现存连接关联 Chrome 的 alive.github.com，但不能仅凭同 IP 断言已结束的旧连接也来自该进程。
- Codex 自身依赖这条代理。排障中退出 v2rayN 导致 Codex 断网，用户重新启动客户端后恢复。此后保持客户端运行，设置菜单自动化不可靠时由用户手动将 TUN stack 从 gvisor 改为 system、保存并仅重启服务。
- 切换前的配置保存在本地私有 work 目录；没有把代理配置或凭据放入 skill。回滚应恢复原 Stack 字段，不覆盖用户后来修改的整个配置。
- 比较切换前后生成的 configPre.json，唯一变化为 `inbounds[0].stack`。日志保持 `warn`，DNS 与路由不变；没有增加屏蔽日志的过滤器。

## 为什么更换实现可能有效

下面的代码与该次安装的依赖版本对应：

1. sing-box 1.14.4 的实际调用路径是 `NewConnection → connectionCopy`。下载方向复制正常结束后，connectionCopy 会对写入端（本地应用的入站连接）调用 `CloseWrite()`；返回错误时，用 `IsClosedOrCanceled` 将它分到 trace 或 error。这里直接产生 `connection download closed:` 日志，因此这行日志并不必然表示拨号失败。[NewConnection](https://github.com/SagerNet/sing-box/blob/v1.14.4/route/conn.go#L153)、[connectionCopy](https://github.com/SagerNet/sing-box/blob/v1.14.4/route/conn.go#L284-L320)
2. gVisor 适配层的 CloseRead/CloseWrite 将底层 Shutdown 错误用 `errors.New(terr.String())` 包装为普通字符串错误。这种包装会丢失可供 errors.Is 判断的底层错误身份。[gVisor 适配层](https://github.com/SagerNet/gvisor/blob/v0.0.0-20260727.0-sing-box-mod.1/pkg/tcpip/adapters/gonet/gonet.go#L398)
3. sing 的关闭错误识别包含标准 `syscall.ENOTCONN`，但同名字符串错误并不因此等同于这个标准错误。[关闭错误分类](https://github.com/SagerNet/sing/blob/5dc452e537bf/common/exceptions/error.go#L47)
4. 该次依赖的 system 实现使用系统 listener 接收 TCP 连接，避开该 gVisor 连接适配路径。[固定版本 system 实现](https://github.com/SagerNet/sing-tun/blob/040db71fcd33/stack_system.go#L376-L389)、[TUN 栈说明](https://sing-box.sagernet.org/configuration/inbound/tun/#stack)

这说明了一个与现场日志吻合的错误分类/兼容性机制，并支持替换实现的处理方向。未对每条历史连接抓包或取得调用栈，不能据此断言每条报错都由同一种关闭竞态引起，或确定是谁先关闭了连接。

切换 system 改变了实际处理连接的实现，保留了原日志配置，但没有修改 gVisor 的源码。标准关闭错误仍可能发生，并被上述实际日志路径识别后归入 trace；warn 订阅看不到这些 trace。现有证据不能区分“关闭方法不再返回错误”和“返回的关闭错误被正确识别为预期状态”，所以不能声称底层关闭错误已消失。如果必须保留 gvisor，需要进一步验证其错误转换路径；不能直接过滤全部 endpoint not connected，也不能把此替代方案称为已修复 gVisor 内部缺陷。

## 当次验证结果与限度

- gvisor 基线观察 45 秒，捕捉到一条同类关闭错误。四次主动取消 TLS 请求均完成，但没有证明这四次取消本身能稳定复现原错误。
- system 下重复四次主动取消 TLS 请求，未观察到同类错误。TUN 与 SOCKS 访问 Google/GitHub 分别得到正常的 204/200；正确域名与 SNI 的 Gmail TLS、IMAP greeting 和 CAPABILITY 验证通过。
- 两段重叠日志订阅的观测跨度超过十一分钟，已连接期间未收到新的 warn/error。首段五分钟；第二段持续到被跟踪的 GitHub 连接已保持 638 秒，仍有新增双向数据。脚本计时早于 WebSocket 建连，且没有累计重连间隙；采样点显示 logConnected=true，不能据此证明全程没有日志盲区。
- Notes 的 993 连接也建立成功并有新增双向数据。没有读取笔记内容，也没有证明账户登录及内容同步全部完成。
- 保持超过十分钟不等于观察到了该连接的正常关闭；因此结论限定为“本次访问回归测试通过，观察窗口内未再收到同类错误”，不能写成“已证实永久根治”“底层关闭错误已经消失”或“任何关闭错误都不会再出现”。

后续复用时先核对当前 sing-box 版本。官方文档已说明较新版本会改变 stack 选项及底层实现，不能盲目套用该次 1.14.4 的设置和源码解释。
