# -*- coding: utf-8 -*-
"""
併發下載模組
使用 ThreadPoolExecutor 實現多執行緒下載
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Callable, Any, Dict
from dataclasses import dataclass
from threading import Lock


@dataclass
class DownloadTask:
    """下載任務"""
    url: str
    file_path: str
    metadata: Dict[str, Any] = None


@dataclass
class DownloadResult:
    """下載結果"""
    task: DownloadTask
    success: bool
    result: Any  # 成功時為檔案大小，失敗時為錯誤訊息
    duration: float  # 下載耗時（秒）


class ConcurrentDownloader:
    """併發下載管理器"""

    def __init__(self, max_workers=5, show_progress=True):
        """
        Args:
            max_workers (int): 最大併發數
            show_progress (bool): 是否顯示進度
        """
        self.max_workers = max_workers
        self.show_progress = show_progress
        self._lock = Lock()
        self._stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'total_size': 0,
            'total_time': 0
        }

    def download_all(
        self,
        tasks: List[DownloadTask],
        download_func: Callable[[Any, str, str], Tuple[bool, Any]],
        session: Any = None
    ) -> List[DownloadResult]:
        """併發下載所有任務

        Args:
            tasks: 下載任務清單
            download_func: 下載函數 (session, url, file_path) -> (success, result)
            session: HTTP session 物件

        Returns:
            List[DownloadResult]: 下載結果清單
        """
        self._stats['total'] = len(tasks)
        results = []

        if self.show_progress:
            self._print_header()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任務
            future_to_task = {
                executor.submit(self._download_task, task, download_func, session): task
                for task in tasks
            }

            # 處理完成的任務
            for future in as_completed(future_to_task):
                result = future.result()
                results.append(result)

                # 更新統計
                self._update_stats(result)

                # 顯示進度
                if self.show_progress:
                    self._print_progress()

        if self.show_progress:
            self._print_summary()

        return results

    def _download_task(
        self,
        task: DownloadTask,
        download_func: Callable,
        session: Any
    ) -> DownloadResult:
        """執行單一下載任務"""
        start_time = time.time()

        try:
            success, result = download_func(session, task.url, task.file_path)
            duration = time.time() - start_time
            return DownloadResult(task, success, result, duration)
        except Exception as e:
            duration = time.time() - start_time
            return DownloadResult(task, False, str(e), duration)

    def _update_stats(self, result: DownloadResult):
        """更新統計資料"""
        with self._lock:
            if result.success:
                self._stats['success'] += 1
                self._stats['total_size'] += result.result
            else:
                self._stats['failed'] += 1
            self._stats['total_time'] += result.duration

    def _print_header(self):
        """顯示表頭"""
        print("\n╔════════════════════════════════════════════════════════════╗")
        print("║               併發下載進行中                                ║")
        print("╚════════════════════════════════════════════════════════════╝")

    def _print_progress(self):
        """顯示進度"""
        completed = self._stats['success'] + self._stats['failed']
        total = self._stats['total']
        percent = (completed / total * 100) if total > 0 else 0

        print(f"\r進度: {completed}/{total} ({percent:.1f}%) | "
              f"成功: {self._stats['success']} | "
              f"失敗: {self._stats['failed']}", end='', flush=True)

    def _print_summary(self):
        """顯示摘要"""
        avg_time = (self._stats['total_time'] / self._stats['total']
                    if self._stats['total'] > 0 else 0)
        total_size_mb = self._stats['total_size'] / (1024 * 1024)

        print("\n\n╔════════════════════════════════════════════════════════════╗")
        print("║               下載完成摘要                                  ║")
        print("╠════════════════════════════════════════════════════════════╣")
        print(f"║  總檔案數: {self._stats['total']}                                            ║")
        print(f"║  成功: {self._stats['success']}                                              ║")
        print(f"║  失敗: {self._stats['failed']}                                              ║")
        print(f"║  總大小: {total_size_mb:.2f} MB                                   ║")
        print(f"║  平均耗時: {avg_time:.2f} 秒                                   ║")
        print("╚════════════════════════════════════════════════════════════╝")

    def get_stats(self) -> Dict[str, Any]:
        """取得統計資料"""
        return self._stats.copy()


# ==================== 輔助函數 ====================

def create_download_tasks(urls_and_paths: List[Tuple[str, str]]) -> List[DownloadTask]:
    """建立下載任務清單

    Args:
        urls_and_paths: [(url, file_path), ...] 清單

    Returns:
        List[DownloadTask]: 任務清單
    """
    return [DownloadTask(url, path) for url, path in urls_and_paths]
