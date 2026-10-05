`timescale 1ns / 1ps
////////////////////////////////////////////////////////////////////////////////
// Design Name: puf-auth-w1
// Module Name: ro_ring
// Description: 
//  奇数反相器环振——"芯片指纹"的最小单元。制造工艺偏差决定它的振荡
//  频率，每颗芯片不同、软件无法仿造。en=1 振荡 / en=0 停振。
//  源码为 5 级反相；布线后网表常被综合器吸收为"LUT2(en) + 3 反相"的
//  4-LUT 环（en=1 常量穿透 DONT_TOUCH，第 5 反相被并入）——仍为奇数环、
//  可振荡、层次名不变，功能等价；实际级数以综合报告为准。
//  KEEP / DONT_TOUCH 属性防止综合器把这个"环形组合逻辑"优化掉。
////////////////////////////////////////////////////////////////////////////////
(* DONT_TOUCH = "true" *) module ro_ring (
    input                   en      ,   // 环振使能：1=振荡
    output                  ro          // 环振输出（异步域信号，仅作计数源）
  );

(* KEEP = "true" *) (* DONT_TOUCH = "true" *) wire  n1;
(* KEEP = "true" *) (* DONT_TOUCH = "true" *) wire  n2;
(* KEEP = "true" *) (* DONT_TOUCH = "true" *) wire  n3;
(* KEEP = "true" *) (* DONT_TOUCH = "true" *) wire  n4;

assign n1 = ~( ro & en );
assign n2 = ~n1;
assign n3 = ~n2;
assign n4 = ~n3;
assign ro  = ~n4;

endmodule
