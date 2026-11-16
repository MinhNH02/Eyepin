#!/usr/bin/env python3
"""SPIKE (ban demo dung mot lan). Tao anh phong to vung mat co luoi toa do goc, de nguoi hoac tro ly AI doc toa do va ghim diem.

  python make_sheet.py <thu_muc_frame> <chi_so_frame> <x0> <y0> <x1> <y1> <anh_ra.png> [he_so_phong=8]
Toa do ghi tren luoi la toa do pixel cua anh goc.
"""
import os, sys, cv2

def make_sheet(frames_dir, index, box, out, k=8, step=5):
    names = sorted(f for f in os.listdir(frames_dir) if f.lower().endswith((".jpg", ".png")))
    img = cv2.imread(os.path.join(frames_dir, names[index]))
    x0, y0, x1, y1 = box
    crop = cv2.resize(img[y0:y1, x0:x1], None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    for x in range(x0 - x0 % step + step, x1, step):
        major = x % (step * 2) == 0
        cv2.line(crop, ((x - x0) * k, 0), ((x - x0) * k, crop.shape[0]), (0, 255, 255) if major else (90, 90, 90), 1)
        if major:
            cv2.putText(crop, str(x), ((x - x0) * k + 2, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1, cv2.LINE_AA)
    for y in range(y0 - y0 % step + step, y1, step):
        major = y % (step * 2) == 0
        cv2.line(crop, (0, (y - y0) * k), (crop.shape[1], (y - y0) * k), (0, 255, 255) if major else (90, 90, 90), 1)
        if major:
            cv2.putText(crop, str(y), (2, (y - y0) * k - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(out, crop)
    return names[index]

if __name__ == "__main__":
    a = sys.argv
    print(make_sheet(a[1], int(a[2]), tuple(int(v) for v in a[3:7]), a[7], int(a[8]) if len(a) > 8 else 8))
