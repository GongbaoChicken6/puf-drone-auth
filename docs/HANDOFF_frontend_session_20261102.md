# D2 前端调优会话交接（2026-11-02 20:40）

## 当前状态

### 已完成（今天全天）
1. **板端实验全部闭环**（详见 data/d1_evidence/）
   - 唯一性验证：完美 2×2 对称矩阵（P1-P4 全过）
   - 无线攻击：板A 5轮 PASS HD=0 + serve CONFIRM；板B 5轮 REJECT 均值144.4 + serve 4帧REJECT
   - 跨板 HD 分布：10轮均值 145.8 (57.0%)
   - 板B 补充：无线自认证5轮全PASS + 重放/c2reset/恢复测试 + 时延数据
2. **M1-M3 纯PC修改**（commit c5e1f96）：阶序守卫+评测三件套+SAC
3. **论文填充材料包**（commit c8a6d06）
4. **web桥串口真实硬件模式**：--serial-port 参数 + RealSerialListener + SSE事件对齐

### 前端调优当前状态（本次会话核心工作）
- **无人机发光材质已修**：emissive .95→.12（源码级，Vite重建，新hash文件名）
- **基站发光已修**：trim .8→.15
- **S1-S7按钮彩色边框+图标**：内嵌脚本（applyStyles），每500ms强制应用
- **文字shadowBlur已删**：改黑色描边+纯白填充
- **标签Y位置已升高**：远离发光体
- **bloomStrength**：在旧JS中设为0（但新build用的是源码默认值1）
- **桥串口口**：COM12（丢石头CH340，板B HC-12 B-PC模块所在口）
  - ⚠ COM6 = LinkE（板A信道），不要用！
- **桥运行命令**：python web/bridge/web_bridge.py --repo-root . --data-dir web/.dev-data --loopback --serial-port COM12 --serial-baud 115200 --port 8642
- **前端地址**：http://127.0.0.1:8642/console.html

### 用户未满意的点（待新对话继续）
1. 3D物体形状仍不够清晰（用户期望更明显细节）
2. 按钮彩色边框在重建后可能丢失（需确认applyStyles脚本在运行的console.html中）
3. SW7按完第一轮后需按SW13复位才能再按（BLOCKED态特性，已告知用户）

### 技术要点
- 前端源码在 web/src/（TypeScript），构建产物在 web/dist/
- 修改源码后需 cd web && npm run build（node_modules已装好）
- 构建会覆盖 web/dist/console.html（需重新注入按钮样式脚本）
- 桥的 RealSerialListener 在 web_bridge.py 的 class RealSerialListener
- SSE事件格式必须匹配前端schema（name/len/msg_id/dir，不是msg_name/length）
- 桥的 --data-dir web/.dev-data 是沙箱（隔离真实数据，铁律不碰真实模板）
- 板B bit是易失的（断电丢失），需重烧：build/board_zc706_seed2/w3_top_zc706_seed2.bit

### Git 状态
- HEAD ≈ 83b6921（前端重建+按钮脚本）
- 本地待推：多个commit（网络间歇，等VPN推）

### 关键COM口映射（2026-11-02 20:35 实测）
- COM6 = VID:PID=1A86:8012 = WCH-LinkE（板A适配器）
- COM12 = VID:PID=1A86:7523 = 丢石头CH340（板B HC-12 B-PC模块）
- 板B JTAG = 210251A04F2C

### 下一步优先级
1. 前端3D效果继续调优（用户不满意当前清晰度）
2. 论文冲刺（D2晚/D3，死线11-03保守）
3. 板子可收起（所有实验数据已落盘）
