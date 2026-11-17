"""Nguồn ảnh của một phiên: Session đọc frame qua một đối tượng nguồn thay vì gắn cứng với thư mục.

Một nguồn có: `names` (tên từng frame), `width`, `height`, `deleted` (frame đã bị xoá sẵn từ nguồn), `key` (khoá ổn định để đặt tên
file phiên), `title` (tên hiện cho người dùng) và `read(i)` trả ảnh BGR của frame i. Ảnh không bao giờ ghi ra đĩa.
"""
from __future__ import annotations

import os

import cv2
import numpy as np

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp")


class DirSource:
    """Thư mục ảnh rời, sắp theo tên theo CHUỖI (`10.png` đứng trước `2.png`), đúng như CVAT (`sorting_method: lexicographical`, cũng là mặc định).
    Số frame trong file XML / file import tính theo thứ tự đó nên KHÔNG sắp tự nhiên: tên không đệm số 0 sẽ lệch frame so với CVAT (lỗi B25)."""

    def __init__(self, folder: str):
        self.folder = folder
        self.names = sorted(f for f in os.listdir(folder) if f.lower().endswith(IMAGE_EXT))
        if not self.names:
            raise ValueError(f"Không có ảnh trong {folder}")
        first = cv2.imread(os.path.join(folder, self.names[0]))
        if first is None:
            raise ValueError(f"Không đọc được ảnh {self.names[0]} trong {folder} (file hỏng hoặc không phải ảnh)")
        self.height, self.width = first.shape[:2]
        self.deleted: set[int] = set()
        self.key = os.path.abspath(folder).lower()
        self.title = os.path.basename(os.path.abspath(folder))

    def read(self, i: int) -> np.ndarray:
        return cv2.imread(os.path.join(self.folder, self.names[i]))
