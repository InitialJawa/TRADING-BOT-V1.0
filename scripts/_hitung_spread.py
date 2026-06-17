# hitung impact spread
old_f = 496545; new_f = 449090; pct_f = (old_f-new_f)/old_f*100
old_e = 199465; new_e = 188038; pct_e = (old_e-new_e)/old_e*100
old_d_roi = 46.9; new_d_roi = 46.04

print("=== IMPAK SPREAD (25 pts XAUUSDm) ===")
print()
print("Strategy F:")
print(f"  Tanpa spread: Rp{old_f:,}/hari")
print(f"  Dengan spread: Rp{new_f:,}/hari")
print(f"  Turun: -Rp{old_f-new_f:,}/hari ({pct_f:.1f}%)")
print(f"  Target Rp300k: {'YA' if new_f >= 300000 else 'TIDAK'} ({new_f/300000*100:.0f}%)")
print()
print("Strategy E:")
print(f"  Tanpa spread: Rp{old_e:,}/hari")
print(f"  Dengan spread: Rp{new_e:,}/hari")
print(f"  Turun: -Rp{old_e-new_e:,}/hari ({pct_e:.1f}%)")
print(f"  Target Rp100k: {'YA' if new_e >= 100000 else 'TIDAK'} ({new_e/100000*100:.0f}%)")
print()
print("Strategy D:")
print(f"  Tanpa spread: +{old_d_roi}% ROI")
print(f"  Dengan spread: +{new_d_roi}% ROI")
print(f"  Turun: {old_d_roi-new_d_roi:.2f} pp")
print()

# Biaya total
print("=== BIAYA TOTAL (4 bulan) ===")
f_spread = 2524 * (25 * 0.01 / 4358 * 12000000)  # approx
f_comm = 2524 * 5000
print(f"F: spread ~Rp{f_spread:,.0f} + komisi Rp{f_comm:,.0f} = Rp{f_spread+f_comm:,.0f}")
e_spread = 1702 * (25 * 0.01 / 4358 * 12000000)
e_comm = 1702 * 5000
print(f"E: spread ~Rp{e_spread:,.0f} + komisi Rp{e_comm:,.0f} = Rp{e_spread+e_comm:,.0f}")
d_spread = 103 * (25 * 0.01 / 4358 * 12000000)
d_comm = 103 * 5000
print(f"D: spread ~Rp{d_spread:,.0f} + komisi Rp{d_comm:,.0f} = Rp{d_spread+d_comm:,.0f}")
