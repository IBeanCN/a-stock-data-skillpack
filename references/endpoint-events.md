# 事件驱动端点（上游 v3.9.0 新增层）

实现位置：`scripts/a_stock_client.py`。六个端点全部走东财数据中心，必须经 `em_get()` 串行限流。

| 端点 | 数据 | 覆盖 |
|---|---|---|
| `earnings_forecast(code=None, report_date=None, limit=500)` | 业绩预告 | 沪深京全市场 |
| `institution_survey(code=None, start=None, end=None, detail=False, limit=500)` | 机构调研 | 沪深京，汇总自投资者关系活动记录表 |
| `holder_trades(code=None, direction=None, start=None, end=None, limit=500)` | 股东增减持 | 沪深京 |
| `share_buyback(code=None, progress=None, limit=500)` | 回购方案与实施进度 | 沪深京 |
| `equity_pledge(code=None, date=None, limit=5000)` | 股权质押比例 | **只覆盖沪深**（中国结算按周统计） |
| `ipo_calendar(limit=100)` | 新股申购日历 | 沪深京，含尚未申购的排期 |

## 严格模式（与其他东财 datacenter 端点的差别）

- 只有第 1 页的「返回数据为空」当空表，其他错误码直接抛错。
- 翻页中途出错、出现空页、非末页不满页、总页数或总条数中途变化、最终条数与总数不符都抛错，不把部分结果当完整结果。
- 返回的顶层或行结构不对（该是对象 / 对象列表却不是）抛 `RuntimeError`；某一行缺必需字段时统一抛带函数名和字段名的 `RuntimeError`，不漏出 `KeyError`。
- 来源自报的页数 / 总数只认整数（JSON 布尔值 `true` 会被 `int()` 当成 1，现在报错），数值字段给了布尔值也报错。
- 来源认不出的数值 / 日期一律抛 `RuntimeError`；`ValueError` 只表示参数错误或确实没有数据。
- `start` 晚于 `end` 在发请求前就抛错；接口忽略筛选条件（返回了窗口外 / 方向不符的行）也抛错。

## 参数与字段

- `earnings_forecast`：`code` 不给是全市场最新 `limit` 条（按公告日倒序），`report_date` 是报告期（如 `'2026-09-30'`）。一次预告会拆成多行，`indicator` 是预告指标（归母净利润 / 扣非净利润 / 营业收入…）。金额单位元，`change_pct_*` 为同比变动 %，`forecast_type` 是预告类型。
- `institution_survey`：`detail=False` 一次调研一行（`org_count` 为参与机构家数）；`detail=True` 一家机构一行，多出 `org_name/org_type/investigators`（很多记录表不写机构类型和人名，为 None）。`start/end` 按公告日 `notice_date` 筛选，`survey_date` 是实际接待日，通常早于公告日几天。
- `holder_trades`：`direction` 取 `None` / `'增持'` / `'减持'`。股数单位万股，`change_shares_10k` 带符号（减持为负）；`*_pct_total` 占总股本 %，`*_pct_float` 占流通股 %。`avg_price` 为公告披露的成交均价，很多公告不披露，为 None；`channel` 是变动方式（二级市场 / 大宗交易 / 协议转让…）。
- `share_buyback`：一个方案一行、按最新公告日倒序。`progress` 取 `None` / `'董事会预案'` / `'股东大会通过'` / `'股东大会否决'` / `'实施中'` / `'停止实施'` / `'完成实施'`。股数单位股、金额单位元，`done_*` 是已回购部分（未开始实施为 None）。东财另有 `007` / `008` 两个进度码（实测 5516 条里 13 条），它自己的页面也不显示名称，这里 `progress` 为 None、`progress_code` 保留原码。
- `equity_pledge`：`code` 给了取该股历次统计（日期倒序），`date` 给了取该统计日全市场，都不给取最近一个统计日；**两个同时给抛 `ValueError`**（不静默丢弃 `date`）。中国结算按周发布（通常为周五），`date` 不是统计日会得到 `ValueError`。`pledge_ratio_pct` 是质押股数占总股本 %；股数单位万股，市值单位万元。实测全市场 2212 条没有一只北交所，传北交所代码直接抛错、不返回空表。
- `ipo_calendar`：按申购日倒序。`issue_price` 在定价前为 None；`issue_shares_10k` 单位万股，`online_shares/apply_upper_shares` 单位股；`top_apply_mktcap_10k` 是顶格申购需配市值（万元）；`win_rate_pct` 是网上中签率 %；`first_close_chg_pct` 是上市首日收盘涨幅 %（未上市为 None）。

## 使用边界

事件类数据是公告的口径（首次披露日、变动区间），不是实时持仓；质押、回购的统计日和公告日要随结果一起说明。全市场默认上限见 `limit`，需要全量时显式调大并接受更长的东财调用时间。
