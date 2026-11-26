# 问题 → 回归测试映射

每个 issue 后面列出对应的测试。**没有测试的修复不算修完**——改前先按 issue 里的复现步骤踩出错误行为，改后必须由这条测试把错误行为钉住。

| issue | 问题 | 对应测试 |
| --- | --- | --- |
| #3 | 金额被行里的其它数字抢走：`iCloud+ 200G` 记成 200、`¥1,288.00` 记成 1 | `tests/test_dingyue.py::TestAmountGreediness`（5 条：`test_storage_number_is_not_amount`、`test_chinese_date_is_not_amount`、`test_chinese_date_alone`、`test_currency_wins_over_bare_number`、`test_plain_number_still_works`）、`TestThousandsSeparator`（3 条）、`tests/test_integration.py::TestHttpLayer::test_scan_numbers` |
| #4 | 首月优惠价被当成常规价 | `TestPromoPrice`（`test_first_month_is_not_regular_price`、`test_promo_note_mentions_first_month`、`test_trial_note`）、`TestHttpLayer::test_scan_flags_promo` |
| #5 | 一次性买断按订阅年化 12 倍，`next` 崩栈 | `TestOneOff`（`test_cycle_is_one_off`、`test_not_multiplied_by_twelve`、`test_no_next_renewal`、`test_excluded_from_annual_total`、`test_not_in_cut_list`）、`TestCliLayer::test_next_skips_one_off` |
| #6 | 「不可退」被判成 7 天可退 | `TestRefundClosed`（`test_virtual_goods_not_refundable`、`test_year_card_still_has_window`、`test_monthly_clause_wins_for_month_plan`、`test_yearly_clause_wins_for_year_plan`） |
| #7 | 「0 次使用」被当成「未填」 | `TestZeroUse`（`test_zero_use_ranks_first`、`test_zero_use_is_not_none`、`test_advice_says_cut_it`）、`TestHttpLayer::test_scan_uses_zero` |
| #8 | `--api-key / --model / --base-url` 不生效 | `tests/test_integration.py::TestModelLayer`（`test_schema_fields`、`test_prompt_carries_schema_numbers`、`test_force_mock_wins_over_key`、`test_money_is_stripped`、`test_empty_model_answer_falls_back_local`） |
| #9 | `--file` 读不到直接 Traceback | `TestCliLayer::test_scan_missing_file_exit_2`、`TestCliLayer::test_scan_empty_text_exit_2` |
| #10 | 网页传字符串次数 500 | `TestHttpLayer::test_scan_uses_zero`（字符串 `"0"` 走完整 HTTP 链路，改前 500） |
| #11 | 未知 POST 路径不读 body 就回 404，客户端偶发收不到（`WinError 10053`） | `TestHttpLayer::test_unknown_post_path_drains_body`（裸 socket 分两段发 40KB，改前稳定失败） |

## 几处说明

- #3 覆盖两层：规则层五条（200G 存储、中文日期、币种优先级）+ 集成层一条（真实报文里 `iCloud+ 200G ¥6.00` 的金额是 6 不是 200）。
- #10 只有入口层能测：规则函数收到字符串就直接炸，是 HTTP 入口把 `"0"` 原样传下去的，所以断言放在 `TestHttpLayer`，跑的是真实 `ThreadingHTTPServer`。
- #11 是集成测试自己偶发红才被抓到的：连跑 8 次全量，改前有一次 `ERROR: test_unknown_path_404`、一次 `WinError 10054`；改后用裸 socket 复现成确定性失败，再修。
