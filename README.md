# 通信原理课设 ADS-B 

## 项目初始目录
```
project/
├── README.md
├── report/
│   ├── ADS-B项目分工细则.docx
│   ├── ADS-B项目分工细则.pdf
│   └── report.md
├── code/
└── figures/
```
## 最终实现文件夹
```
ADS-B原型系统/
│
├── code/
│   ├── adsb_frame.py
│   ├── transmitter.py
│   ├── receiver.py
│   ├── ber_analysis.py
│
├── gnuradio/
│   ├── adsb_awgn_channel.grc
│
├── data/
│   ├── adsb_frame_bits.txt
│   ├── tx_bits.txt
│   ├── tx_samples.dat
│   ├── rx_samples_snr20.dat
│   ├── rx_samples_snr10.dat
│   ├── rx_samples_snr5.dat
│   ├── rx_samples_snr0.dat
│
├── results/
│   ├── decoded_aircraft_state_snr20.txt
│   ├── decoded_aircraft_state_snr10.txt
│   ├── decoded_aircraft_state_snr5.txt
│   ├── decoded_aircraft_state_snr0.txt
│   ├── ber_result.csv
│   ├── experiment_summary.xlsx
│
├── figures/
│   ├── system_block_diagram.png
│   ├── gnuradio_flowgraph.png
│   ├── tx_waveform.png
│   ├── tx_spectrum.png
│   ├── rx_waveform_snr20.png
│   ├── rx_waveform_snr10.png
│   ├── rx_waveform_snr5.png
│   ├── rx_waveform_snr0.png
│   ├── ber_curve.png
│
├── docs/
│   ├── ADS-B_Mode-S理论调研.docx
│   ├── 报文结构设计说明.docx
│   ├── 发送端模块说明.docx
│   ├── AWGN信道模块说明.docx
│   ├── 接收端模块说明.docx
│
├── report/
│   ├── 综合实验报告.docx
│   ├── AI工具使用说明.docx
│
└── references/
    ├── 参考文献列表.docx
```
## 文档说明
docx：最终提交版
md：便于 Git 管理的编辑版
pdf：便于预览和展示