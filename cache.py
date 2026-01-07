# -*- coding: utf-8 -*-
"""
快取管理模組
實現下載記錄快取，避免重複下載
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any


class DownloadCache:
    """下載快取管理器"""

    def __init__(self, cache_file='.download_cache.json'):
        """
        Args:
            cache_file (str): 快取檔案路徑
        """
        self.cache_file = Path(__file__).parent / cache_file
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        """載入快取"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 載入快取失敗: {e}")
        return {}

    def _save_cache(self):
        """儲存快取"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 儲存快取失敗: {e}")

    def _generate_key(self, url: str, file_path: str) -> str:
        """生成快取鍵值

        Args:
            url: 下載 URL
            file_path: 檔案路徑

        Returns:
            str: MD5 雜湊鍵值
        """
        key_string = f"{url}:{file_path}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def is_downloaded(self, url: str, file_path: str) -> bool:
        """檢查是否已下載

        Args:
            url: 下載 URL
            file_path: 檔案路徑

        Returns:
            bool: 是否已下載
        """
        key = self._generate_key(url, file_path)

        if key not in self.cache:
            return False

        # 檢查檔案是否仍存在
        if not Path(file_path).exists():
            # 檔案不存在，移除快取記錄
            del self.cache[key]
            self._save_cache()
            return False

        return True

    def mark_downloaded(
        self,
        url: str,
        file_path: str,
        file_size: int,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """標記為已下載

        Args:
            url: 下載 URL
            file_path: 檔案路徑
            file_size: 檔案大小（bytes）
            metadata: 額外的元資料
        """
        key = self._generate_key(url, file_path)
        self.cache[key] = {
            'url': url,
            'file_path': file_path,
            'file_size': file_size,
            'downloaded_at': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        self._save_cache()

    def get_info(self, url: str, file_path: str) -> Optional[Dict[str, Any]]:
        """取得快取資訊

        Args:
            url: 下載 URL
            file_path: 檔案路徑

        Returns:
            Optional[Dict]: 快取資訊，若不存在返回 None
        """
        key = self._generate_key(url, file_path)
        return self.cache.get(key)

    def clear_cache(self):
        """清除所有快取"""
        self.cache = {}
        self._save_cache()

    def get_stats(self) -> Dict[str, Any]:
        """取得快取統計

        Returns:
            Dict: 統計資訊
        """
        total_size = sum(item.get('file_size', 0) for item in self.cache.values())
        return {
            'total_files': len(self.cache),
            'total_size': total_size,
            'total_size_mb': total_size / (1024 * 1024)
        }

    def remove_missing_files(self) -> int:
        """移除不存在檔案的快取記錄

        Returns:
            int: 移除的記錄數
        """
        removed = 0
        keys_to_remove = []

        for key, info in self.cache.items():
            if not Path(info['file_path']).exists():
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.cache[key]
            removed += 1

        if removed > 0:
            self._save_cache()

        return removed


# 全域快取實例
cache = DownloadCache()
