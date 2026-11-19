# PUF 唯一性实验：同 bit 双板指纹对比（2026-11-19 16:05）

## 实验配置
- 板A(210251A0195C/COM6/C001) 与 板B(210251A04F2C/COM11/C006) 烧录**同一个** production bit
  (build/board_zc706/w3_top_zc706.bit, 2026-11-13 构建, PROGRAM_OK x2)
- 固定挑战种子 2 组(S1/S2, 各 4x8B), 每组每板重复 2 次
- 裸串口 5 帧:AUTH_POLL->ACCESS_REQUEST->CHALLENGE(固定种子)->RESPONSE_R1

## 原始指纹(32B = 4x8B R1)
A S1 #1: 9a4f4dfa71a2de2f31a84d6921809750d86d5c4122b05f9870300c4233b1c2bd
A S1 #2: 9a4f4dfa61a2de2f31a84d6921809750d86d5c6122b05f9870300c4233b1c2bd
A S2 #1: 94895c4a3b82390a2e915d7a1211db7ba6a65c4a25d5f83042294d4bf270cdd3
A S2 #2: 94895c4a3b82390a2e915d7a12159b7b26a65c4a25d5f83042294d4bf270cdd3
B S1 #1: da4f4d5a71a25e2f31884d69618095d0d86d5c5162b05f9c60300c4233b1c2bd
B S1 #2: da4f4d5a71a25e2f31884d69618095d0d86d5c5162b05f9c60300c4233b1c2bd
B S2 #1: 849b5c6bba82190a2e915d5a12059b7b36a65c4a2591f83242294d4bd270edd3
B S2 #2: 849b5c6bba82190a2e915d5a12059b7b36a65c4a2591f83242294d4bd270edd3

## 分析
| 指标 | HD(/256bit) |
|---|---|
| 板间 S1 | 12 |
| 板间 S2 | 19 |
| 板A 组内重复 | 2-3(噪声) |
| 板B 组内重复 | 0(完全稳定) |

## 结论
1. 同 bit 双板指纹**不相同**(HD 12-19, ~5-7% 位差) —— RO-PUF 工艺偏差真实存在
2. 但差异 **远低于认证 PASS 阈值**(scaled_pass=24): 用 A 模板验 B 响应会判 PASS
   = "同配置可整板克隆"漏洞的定量复现(与 11 月上旬实测 HD 0~1 同一现象, 今天偏大但同量级)
3. 板间差异稳定可重复(组内 A 2-3bit 噪声、B 0bit) —— 差异来自制造, 非测量噪声
4. 与 Maiti(HOST 2010) 结论一致: 同布局下工艺偏差不足以区分 RO 排序
   => 一机一布局(seed2 差异化)是唯一性的保证, 论文 §1.3/创新点(2) 口径成立

## 注意
实验后两板均为 production bit; 演示需恢复 板A=v4 bit+ELF / 板B=seed2 bit。
