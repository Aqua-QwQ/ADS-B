import numpy as np
import sys
import csv
import matplotlib.pyplot as plt
from pathlib import Path

current_dir = Path(__file__).parent.absolute()
project_root = current_dir.parent
sys.path.insert(0, str(project_root))

from adsb_frame import parse_frame_fields

plt.rcParams['axes.unicode_minus'] = False

data_dir = project_root / "data"
results_dir = project_root / "results"
figures_dir = project_root / "figures"

results_dir.mkdir(exist_ok=True)
figures_dir.mkdir(exist_ok=True)

PREAMBLE_STR = "1010000101000000"
FRAME_BITS = 128
MESSAGE_BITS = 112
SAMPLES_PER_BIT = 2


def read_samples(filepath):
    """
    读取采样文件
    参数: filepath - 文件路径
    返回: numpy数组，dtype=float32
    """
    return np.fromfile(filepath, dtype=np.float32)


def ppm_demodulate(samples):
    """
    PPM解调
    映射规则: bit 1 -> [1, 0], bit 0 -> [0, 1]
    参数: samples - 采样点数组
    返回: 解调后的比特列表
    """
    bits = []
    num_bits = len(samples) // SAMPLES_PER_BIT

    for i in range(num_bits):
        s1 = samples[i * SAMPLES_PER_BIT]
        s2 = samples[i * SAMPLES_PER_BIT + 1]
        bits.append(1 if s1 > s2 else 0)

    return bits


def detect_preamble(bits, preamble_str):
    """
    检测前导码
    参数: bits - 解调后的比特列表
          preamble_str - 前导码字符串
    返回: (最佳位置, 匹配度)
    """
    preamble = [int(b) for b in preamble_str]
    best_pos = -1
    best_matches = 0

    for pos in range(len(bits) - 16):
        matches = sum(1 for j in range(16) if bits[pos + j] == preamble[j])
        if matches > best_matches:
            best_matches = matches
            best_pos = pos
            if matches == 16:
                break

    return best_pos, best_matches


def calculate_ber(tx_bits, rx_bits):
    """
    计算误码率
    参数: tx_bits - 发送端比特列表
          rx_bits - 接收端比特列表
    返回: (错误数, 误码率)
    """
    if len(tx_bits) != len(rx_bits):
        min_len = min(len(tx_bits), len(rx_bits))
        tx_bits = tx_bits[:min_len]
        rx_bits = rx_bits[:min_len]

    errors = sum(1 for i in range(len(tx_bits)) if tx_bits[i] != rx_bits[i])
    ber = errors / len(tx_bits) if len(tx_bits) > 0 else 1.0

    return errors, ber


def theoretical_ber(snr_db):
    """
    计算BPSK在AWGN信道下的理论BER
    参数: snr_db - 信噪比(dB)
    返回: 理论误码率
    """
    snr_linear = 10 ** (snr_db / 10)
    ber = 0.5 * (1 - np.sqrt(snr_linear / (1 + snr_linear)))
    return max(ber, 1e-10)


def main():
    """
    主函数: 处理所有SNR的接收信号，输出解码日志和BER曲线
    """
    print("=" * 70)
    print("ADS-B 1090ES Receiver Processing")
    print("=" * 70)
    print(f"Project root: {project_root}")
    print()

    tx_file = data_dir / "tx_bits.txt"
    if not tx_file.exists():
        print(f"Error: {tx_file} not found!")
        print("Please ensure the data directory contains tx_bits.txt")
        return

    with open(tx_file, 'r') as f:
        tx_bits_str = f.read().strip()

    tx_bits = [int(b) for b in tx_bits_str]
    tx_preamble = tx_bits_str[:16]

    print(f"TX Preamble: {tx_preamble}")
    print(f"TX Message length: {len(tx_bits_str[16:])} bits")
    print()

    snr_list = [20, 10, 5, 0]
    results = []

    for snr in snr_list:
        samples_file = data_dir / f"rx_samples_snr{snr}.dat"

        print(f"\n{'=' * 50}")
        print(f"Processing SNR = {snr} dB")
        print(f"{'=' * 50}")

        if not samples_file.exists():
            print(f"  [ERROR] File not found: {samples_file}")
            continue

        samples = read_samples(samples_file)
        print(f"  [OK] Samples: {len(samples)}")

        rx_bits = ppm_demodulate(samples)
        print(f"  [OK] Demodulated bits: {len(rx_bits)}")

        pos, matches = detect_preamble(rx_bits, tx_preamble)

        if pos == -1:
            print(f"  [FAIL] Preamble not found")
            continue

        print(f"  [OK] Preamble position: {pos}, matches: {matches}/16")

        frame = rx_bits[pos:pos + FRAME_BITS]
        errors, ber = calculate_ber(tx_bits, frame)
        print(f"  [OK] BER: {ber:.6f} ({errors}/{FRAME_BITS})")

        message_bits = frame[16:128]
        try:
            decoded = parse_frame_fields(message_bits)
            crc_ok = decoded['crc_ok']
            print(f"  [OK] CRC: {'PASS' if crc_ok else 'FAIL'}")

            if crc_ok:
                print(f"       ICAO: {hex(decoded['icao'])}")
                print(f"       Altitude: {decoded['altitude']} ft")
                print(f"       Speed: {decoded['speed']} knots")
                print(f"       Heading: {decoded['heading']} deg")
        except Exception as e:
            crc_ok = False
            decoded = {}
            print(f"  [FAIL] Parse error: {e}")

        log_file = results_dir / f"decode_log_snr{snr}.txt"
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write(f"ADS-B Decode Log - SNR = {snr} dB\n")
            f.write("=" * 60 + "\n\n")

            f.write("[Preamble Detection]\n")
            f.write(f"  Position: {pos}\n")
            f.write(f"  Matches: {matches}/16\n\n")

            f.write("[BER Statistics]\n")
            f.write(f"  Total bits: {FRAME_BITS}\n")
            f.write(f"  Error bits: {errors}\n")
            f.write(f"  BER: {ber:.6f}\n\n")

            f.write("[Message Decoding]\n")
            f.write(f"  CRC: {'PASS' if crc_ok else 'FAIL'}\n")
            if crc_ok:
                f.write(f"  ICAO: {hex(decoded.get('icao', 0))}\n")
                f.write(f"  Altitude: {decoded.get('altitude', 0)} ft\n")
                f.write(f"  Speed: {decoded.get('speed', 0)} knots\n")
                f.write(f"  Heading: {decoded.get('heading', 0)} deg\n")
                f.write(f"  Latitude: {decoded.get('latitude', 0)} deg\n")
                f.write(f"  Longitude: {decoded.get('longitude', 0)} deg\n")

        print(f"  [SAVED] {log_file.name}")

        results.append({
            'snr': snr,
            'pos': pos,
            'matches': matches,
            'ber': ber,
            'errors': errors,
            'crc_ok': crc_ok
        })

    ber_csv_file = results_dir / "ber_stat.csv"
    with open(ber_csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['SNR_dB', 'BER', 'Errors', 'Total_Bits', 'CRC_OK'])
        for r in results:
            writer.writerow([
                r['snr'],
                f"{r['ber']:.6f}",
                r['errors'],
                FRAME_BITS,
                'Yes' if r['crc_ok'] else 'No'
            ])
    print(f"\n[SAVED] {ber_csv_file.name}")

    if results:
        plt.figure(figsize=(10, 6))

        snr_actual = [r['snr'] for r in results]
        ber_actual = [r['ber'] for r in results]

        snr_theory = np.linspace(0, 20, 100)
        ber_theory = [theoretical_ber(s) for s in snr_theory]

        plt.semilogy(snr_theory, ber_theory, 'b-', linewidth=2, label='Theoretical BER (BPSK in AWGN)')
        plt.semilogy(snr_actual, ber_actual, 'ro-', linewidth=2, markersize=8, label='Measured BER')

        for snr, ber in zip(snr_actual, ber_actual):
            plt.annotate(f'{ber:.4f}', (snr, ber), textcoords="offset points", xytext=(5, 10), ha='center')

        plt.xlabel('SNR (dB)', fontsize=12)
        plt.ylabel('Bit Error Rate (BER)', fontsize=12)
        plt.title('ADS-B 1090ES System BER-SNR Curve', fontsize=14)
        plt.grid(True, alpha=0.3)
        plt.legend(loc='upper right', fontsize=10)
        plt.xlim(0, 20)
        plt.ylim(1e-6, 1)

        ber_curve_file = figures_dir / "ber_curve.png"
        plt.savefig(ber_curve_file, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"[SAVED] {ber_curve_file.name}")

    print("\n" + "=" * 70)
    print("Experimental Results Summary")
    print("=" * 70)
    print(f"{'SNR(dB)':<10} {'Preamble Pos':<14} {'Matches':<10} {'BER':<15} {'CRC':<8}")
    print("-" * 65)
    for r in results:
        crc_status = "PASS" if r['crc_ok'] else "FAIL"
        print(f"{r['snr']:<10} {r['pos']:<14} {r['matches']}/16      {r['ber']:.6f}    {crc_status}")

    print("\n" + "=" * 70)
    print("Output Files Summary")
    print("=" * 70)
    print("\n[results/] folder:")
    print("  - ber_stat.csv (BER statistics table)")
    for snr in snr_list:
        print(f"  - decode_log_snr{snr}.txt (Decode log)")
    print("\n[figures/] folder:")
    print("  - ber_curve.png (BER-SNR curve)")

    print("\n[DONE] Receiver processing completed successfully!")


if __name__ == "__main__":
    main()