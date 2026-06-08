# -*- coding: utf-8 -*-
"""全站同品检测工具 - GUI界面 (tkinter)"""

import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime

from config import OUTPUT_DATE_FORMAT, OUTPUT_FILE_PREFIX
from processor import SameProductProcessor


class SameProductApp:
    """全站同品检测工具 GUI 应用"""

    def __init__(self, root):
        self.root = root
        self.root.title("全站同品检测工具 v1.0")
        self.root.geometry("720x620")
        self.root.resizable(True, True)
        self.root.minsize(600, 500)

        self.processor = None
        self.worker_thread = None
        self.msg_queue = queue.Queue()
        self.is_running = False

        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ---- 标题 ----
        title_label = ttk.Label(main_frame, text="全站同品检测工具", font=("Microsoft YaHei", 16, "bold"))
        title_label.pack(pady=(0, 10))

        # ---- 文件选择区 ----
        file_frame = ttk.LabelFrame(main_frame, text="输入文件", padding=8)
        file_frame.pack(fill=tk.X, pady=(0, 8))

        self.file_var = tk.StringVar()
        file_entry = ttk.Entry(file_frame, textvariable=self.file_var)
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        browse_btn = ttk.Button(file_frame, text="浏览...", command=self._browse_file)
        browse_btn.pack(side=tk.RIGHT)

        # ---- 控制按钮区 ----
        ctrl_frame = ttk.Frame(main_frame)
        ctrl_frame.pack(fill=tk.X, pady=(0, 8))

        self.start_btn = ttk.Button(ctrl_frame, text="▶ 开始匹配", command=self._start_processing)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.stop_btn = ttk.Button(ctrl_frame, text="⏹ 停止", command=self._stop_processing, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)

        self.status_label = ttk.Label(ctrl_frame, text="就绪", foreground="gray")
        self.status_label.pack(side=tk.RIGHT)

        # ---- 进度条 ----
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 8))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame, variable=self.progress_var, maximum=100, mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X)

        self.progress_label = ttk.Label(progress_frame, text="")
        self.progress_label.pack(anchor=tk.W)

        # ---- 日志区 ----
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, wrap=tk.WORD,
            font=("Consolas", 9), state=tk.DISABLED,
            background="#1e1e1e", foreground="#d4d4d4"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # ---- 导出区 ----
        export_frame = ttk.LabelFrame(main_frame, text="导出结果", padding=8)
        export_frame.pack(fill=tk.X)

        self.export_var = tk.StringVar()
        default_name = OUTPUT_FILE_PREFIX + datetime.now().strftime(OUTPUT_DATE_FORMAT) + ".xlsx"
        self.export_var.set(default_name)

        export_entry = ttk.Entry(export_frame, textvariable=self.export_var)
        export_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(export_frame, text="浏览...", command=self._browse_export).pack(side=tk.RIGHT, padx=(0, 5))
        self.export_btn = ttk.Button(
            export_frame, text="导出Excel", command=self._export_results, state=tk.DISABLED
        )
        self.export_btn.pack(side=tk.RIGHT)

    # ==================== 文件选择 ====================

    def _browse_file(self):
        file_path = filedialog.askopenfilename(
            title="选择种子SKU文件",
            filetypes=[("Excel文件", "*.xlsx"), ("Excel 97-2003", "*.xls"), ("所有文件", "*.*")]
        )
        if file_path:
            self.file_var.set(file_path)

    def _browse_export(self):
        file_path = filedialog.asksaveasfilename(
            title="保存匹配结果",
            defaultextension=".xlsx",
            filetypes=[("Excel文件", "*.xlsx")],
            initialfile=self.export_var.get()
        )
        if file_path:
            self.export_var.set(file_path)

    # ==================== 日志显示 ====================

    def _append_log(self, message):
        self.msg_queue.put(('log', message))

    def _update_progress(self, step, current, total, message=''):
        self.msg_queue.put(('progress', (step, current, total, message)))

    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == 'log':
                    self.log_text.config(state=tk.NORMAL)
                    self.log_text.insert(tk.END, data + '\n')
                    self.log_text.see(tk.END)
                    self.log_text.config(state=tk.DISABLED)
                elif msg_type == 'progress':
                    step, current, total, message = data
                    if total > 0:
                        pct = current / total * 100
                        self.progress_var.set(pct)
                        self.progress_label.config(text=f"步骤{step} | {current}/{total} | {message}")
                    if '完成' in message or '✅' in message:
                        self.status_label.config(text=message, foreground="green")
                    else:
                        self.status_label.config(text=f"步骤{step}: {message}", foreground="blue")
                elif msg_type == 'done':
                    success = data
                    self.is_running = False
                    self.start_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)
                    if success:
                        self.export_btn.config(state=tk.NORMAL)
                        self.status_label.config(text="✅ 匹配完成，可导出结果", foreground="green")
                        self.progress_var.set(100)
                    else:
                        self.status_label.config(text="❌ 匹配失败或已停止", foreground="red")
        except queue.Empty:
            pass

        self.root.after(100, self._poll_queue)

    # ==================== 处理控制 ====================

    def _start_processing(self):
        input_file = self.file_var.get().strip()
        if not input_file:
            messagebox.showwarning("提示", "请先选择种子SKU文件")
            return
        if not os.path.isfile(input_file):
            messagebox.showerror("错误", f"文件不存在: {input_file}")
            return

        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.DISABLED)
        self.progress_var.set(0)
        self.status_label.config(text="运行中...", foreground="blue")

        # 清空日志
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

        self.processor = SameProductProcessor(
            progress_callback=self._update_progress,
            log_callback=self._append_log,
        )

        output_path = self.export_var.get().strip()
        self.worker_thread = threading.Thread(
            target=self._run_pipeline,
            args=(input_file, output_path),
            daemon=True
        )
        self.worker_thread.start()

    def _run_pipeline(self, input_file, output_path):
        try:
            success = self.processor.run_full_pipeline(input_file, output_path)
            self.msg_queue.put(('done', success))
        except Exception as e:
            self._append_log(f"❌ 致命错误: {e}")
            self.msg_queue.put(('done', False))

    def _stop_processing(self):
        if self.processor:
            self.processor.request_stop()
        self.stop_btn.config(state=tk.DISABLED)

    # ==================== 导出结果 ====================

    def _export_results(self):
        if not self.processor:
            messagebox.showwarning("提示", "没有可导出的结果")
            return

        output_path = self.export_var.get().strip()
        if not output_path:
            messagebox.showwarning("提示", "请指定导出文件路径")
            return

        try:
            self.processor.export_results(output_path)
            messagebox.showinfo("成功", f"结果已导出到:\n{output_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))


def main():
    root = tk.Tk()
    app = SameProductApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
