# 全站同品检测工具

基于京东内部同品匹配服务的本地化 Windows 工具，无需安装 Python 环境，双击即可运行。

## 功能说明

1. **上传种子SKU文件** — 支持 `.xlsx` 格式，自动识别 sku_id 列
2. **查询SKU信息** — 通过 JSF 接口获取品牌、型号、颜色、尺寸等属性
3. **搜索召回** — 按关键词在全站搜索相似SKU
4. **获取召回详情** — 批量查询召回SKU的详细信息和兄弟映射
5. **特征计算** — 调用算法服务计算SKU特征向量
6. **同品匹配** — 高召 + 高准匹配，输出同品对
7. **导出结果** — 自动生成 Excel，含种子信息、召回结果、匹配明细三个 Sheet

## 使用前提

- Windows 10/11 64 位
- 能访问京东内网（`*.jd.local`, `*.jdindustry.com`）

## 快速使用

1. 双击 `全站同品检测工具.exe` 启动
2. 点击「浏览」选择种子SKU的 Excel 文件
3. 点击「开始匹配」
4. 等待处理完成，点击「导出Excel」保存结果

## 输出文件

自动命名格式：`匹配结果_年月日.xlsx`

| Sheet | 内容 |
|-------|------|
| 种子SKU信息 | 种子SKU的基本属性和匹配数量 |
| 召回结果 | 搜索召回的全部SKU列表 |
| 匹配结果 | 高召/高准同品匹配明细 |

## 从源码构建

### 本地构建（需 Windows + Python 3.9）

```bash
pip install -r requirements.txt
pip install pyinstaller
build.bat
```

### GitHub Actions 自动构建

1. 将代码推送到 GitHub 仓库
2. 进入 Actions 页面，手动触发 "Build Windows EXE" 工作流
3. 构建完成后在 Artifacts 中下载 exe 文件

## 技术栈

- GUI: tkinter
- Excel: pandas + openpyxl
- HTTP: requests
- 打包: PyInstaller

## 注意事项

- 本工具仅在京东内网环境下可用
- 接口调用自动限流，无需手动调整
- 单条失败不影响整体流程
- 支持中途停止
