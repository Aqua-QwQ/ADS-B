# ADS-B 1090ES 基带通信原型系统

本项目是通信原理课程实验的 ADS-B 1090ES 基带链路原型。系统从虚拟飞机状态出发，完成 ADS-B 报文生成、前导码添加、PPM 调制、AWGN 信道传输、接收端解调、CRC 校验和 BER 统计。

整体流程：

```text
虚拟飞机状态
  -> ADS-B 112 bit 报文生成
  -> 添加 16 bit 前导码
  -> PPM 调制生成基带采样
  -> AWGN 信道
  -> PPM 解调与前导码检测
  -> CRC 校验与字段解析
  -> BER 统计与图像输出
```

说明：本项目的 ME 字段采用课程实验用的简化编码，用固定位宽存放高度、速度、航向、经纬度等信息；CRC-24 和 112 bit 外层结构按 Mode-S 形式实现，但不等同于完整真实航空 ADS-B 标准。

## 环境要求

建议使用 Python 3.9 或更高版本。主要依赖：

```text
numpy
matplotlib
```

如果当前环境缺少依赖，可安装：

```bash
pip install numpy matplotlib
```

## 一键运行

推荐直接运行：

```bash
python code/run_all.py
```

该命令会自动执行：

```text
1. transmitter.py 生成发送端数据
2. awgn_channel.py 生成不同 SNR 下的接收采样
3. receiver.py 解调、CRC 校验、BER 统计
```

默认参数：

```text
发送模式: multi
SNR: 20 10 5 0 dB
随机种子: 2026
配置文件: config/aircraft_scenario.json
```

常用示例：

```bash
# 默认多帧轨迹模式，并刷新单帧接口
python code/run_all.py

# 只生成单帧发送数据再跑完整链路
python code/run_all.py --mode single

# 指定 SNR
python code/run_all.py --snr 30 20 10 5 0

# 不重新生成接收波形/频谱图
python code/run_all.py --no-plots

# 指定随机种子，保证噪声可复现
python code/run_all.py --seed 123
```

运行结束后，终端会输出各 SNR 下的前导码匹配、BER 和 CRC 结果。

## 分步运行

如果需要单独调试每个模块，可以按下面顺序运行。

### 1. 发送端

单帧模式：

```bash
python code/transmitter.py --mode single
```

多帧轨迹模式：

```bash
python code/transmitter.py --mode multi --config config/aircraft_scenario.json
```

主要输出：

```text
data/adsb_frame_bits.txt
data/tx_bits.txt
data/tx_samples.dat
data/tx_state.txt
figures/tx_waveform.png
figures/tx_spectrum.png
```

多帧模式还会输出：

```text
data/tx_states.csv
data/adsb_frame_bits_multi.txt
data/tx_bits_multi.txt
data/tx_samples_multi.dat
figures/aircraft_trajectory.png
figures/altitude_speed_heading.png
figures/tx_waveform_multi.png
```

### 2. AWGN 信道

```bash
python code/awgn_channel.py --snr 20 10 5 0
```

主要输出：

```text
data/rx_samples_snr20.dat
data/rx_samples_snr10.dat
data/rx_samples_snr5.dat
data/rx_samples_snr0.dat
figures/rx_waveform_snr*.png
figures/rx_spectrum_snr*.png
```

### 3. 接收端

```bash
python code/receiver.py
```

主要输出：

```text
results/decode_log_snr20.txt
results/decode_log_snr10.txt
results/decode_log_snr5.txt
results/decode_log_snr0.txt
results/ber_stat.csv
figures/ber_curve.png
```

## 项目目录

```text
ADS-B/
├── README.md
├── .gitignore
├── code/
│   ├── adsb_frame.py          # ADS-B 报文生成、解析、CRC-24
│   ├── transmitter.py         # 飞机状态生成、前导码添加、PPM 调制
│   ├── awgn_channel.py        # 纯 Python AWGN 信道批处理
│   ├── receiver.py            # PPM 解调、前导码检测、CRC 校验、BER 统计
│   ├── run_all.py             # 一键运行入口
│   ├── test_adsb_frame.py     # 协议层单元测试
│   ├── test_awgn_channel.py   # AWGN 信道单元测试
│   └── test_interface.py      # 成员接口适配检查
├── config/
│   └── aircraft_scenario.json # 多帧飞机轨迹配置
├── data/
│   ├── adsb_frame_bits.txt
│   ├── tx_bits.txt
│   ├── tx_samples.dat
│   ├── tx_states.csv
│   ├── tx_samples_multi.dat
│   └── rx_samples_snr*.dat
├── results/
│   ├── ber_stat.csv
│   ├── decode_log_snr*.txt
│   └── decoded_aircraft_state_snr*.txt
├── figures/
│   ├── tx_waveform.png
│   ├── tx_spectrum.png
│   ├── rx_waveform_snr*.png
│   ├── rx_spectrum_snr*.png
│   ├── ber_curve.png
│   ├── aircraft_trajectory.png
│   ├── altitude_speed_heading.png
│   └── preamble_detection.png
├── gnuradio/
│   ├── adsb_awgn_channel.grc
│   └── adsb_awgn_channel.py
├── docs/
│   ├── ADS-B_Mode-S理论调研.md
│   ├── 报文结构设计说明.md
│   └── 发送端模块说明.md
├── report/
│   ├── report.md
│   ├── ADS-B项目分工细则.docx
│   └── ADS-B项目分工细则.pdf
└── run/
    └── run*.png
```

## 核心模块说明

### `adsb_frame.py`

负责 ADS-B 报文层处理：

```text
飞机状态 -> 56 bit ME 字段 -> 88 bit payload -> CRC-24 -> 112 bit 报文
```

主要函数：

```text
generate_adsb_frame(state)
parse_frame_fields(bits)
generate_crc24(bits)
```

### `transmitter.py`

负责发送端处理：

```text
112 bit ADS-B 报文
  -> 添加 16 bit 前导码
  -> 128 bit 发送比特流
  -> PPM 调制
  -> 256 个 float32 采样点
```

PPM 映射规则：

```text
bit 1 -> [1, 0]
bit 0 -> [0, 1]
```

### `awgn_channel.py`

负责添加加性高斯白噪声：

```text
r = s + n
```

其中 `s` 是发送采样，`n` 是按指定 SNR 生成的高斯噪声。

### `receiver.py`

负责接收端处理：

```text
接收采样
  -> PPM 解调
  -> 前导码检测
  -> 截取 112 bit ADS-B 报文
  -> CRC 校验
  -> 字段解析
  -> BER 统计
```

## 测试

运行协议层测试：

```bash
python code/test_adsb_frame.py
```

运行 AWGN 信道测试：

```bash
python code/test_awgn_channel.py
```

运行接口检查：

```bash
python code/test_interface.py
```

## 当前结果示例

默认一键运行后，`results/ber_stat.csv` 示例：

```text
SNR_dB,BER,Errors,Total_Bits,CRC_OK
20,0.000000,0,128,Yes
10,0.000000,0,128,Yes
5,0.031250,4,128,No
0,0.156250,20,128,No
```

由于每个 SNR 默认只统计一帧 128 bit，该 BER 是单次实验观测值；如果需要更稳定的 BER 曲线，应增加多帧统计或 Monte Carlo 仿真。
