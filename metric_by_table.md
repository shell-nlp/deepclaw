# 按 table_name 汇总——每张表能出哪些指标

共涉及 **23** 张来源表，**731** 个指标。

## TB_KR_FM_SK_ZDYW_FZ_KD_DAY（共 231 个指标）

### 场景：维度：SK

- **涉及字段**：`SK_BYJG_ORDER_CNTS`, `SK_BYJG_ORDER_JGL`, `SK_BY_ORDER_CNTS`, `SK_KD_DNEW_CNT`, `SK_KD_MJZ_CNT`, `SK_KD_MJZ_CNT_HB`, `SK_KD_MJZ_CNT_SYD`, `SK_KD_MJZ_CNT_SYD_HB`, `SK_KD_MNEW1000_CNT`, `SK_KD_MNEW1000_CNT_ZB`, `SK_KD_MNEW100_CNT`, `SK_KD_MNEW100_CNT_ZB`, `SK_KD_MNEW200_CNT`, `SK_KD_MNEW200_CNT_ZB`, `SK_KD_MNEW300_CNT`, `SK_KD_MNEW300_CNT_ZB`, `SK_KD_MNEW500_CNT`, `SK_KD_MNEW500_CNT_ZB`, `SK_KD_MNEW_CNT`, `SK_KD_MNEW_CNT_HB`, `SK_KD_MNEW_CNT_ZB`, `SK_KD_MNEW_HKRH_CNT`, `SK_KD_MNEW_HYCNT`, `SK_KD_MNEW_HYL`, `SK_KD_MNEW_HYL1`, `SK_KD_QM1000_CNT`, `SK_KD_QM1000_CNT_ZB`, `SK_KD_QM100_CNT`, `SK_KD_QM100_CNT_ZB`, `SK_KD_QM200_CNT`, `SK_KD_QM200_CNT_ZB`, `SK_KD_QM300_CNT`, `SK_KD_QM300_CNT_ZB`, `SK_KD_QM500_CNT`, `SK_KD_QM500_CNT_ZB`, `SK_KD_QM_CNT`, `SK_KD_QM_CNT_HB`, `SK_KD_QM_HYCNT`, `SK_KD_QM_HYCNT1`, `SK_KD_QM_HYL`, `SK_PORTS_CNT`, `SK_PORTS_LYL`, `SK_WZGMKD_QM_CNT`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（43 个）**：
  - 商客宽带较上月同期净增数（`SK_KD_MJZ_CNT`）
  - 商客宽带较上月同期净增环比（`SK_KD_MJZ_CNT_HB`）
  - 宽带当日新增量（`SK_KD_DNEW_CNT`）
  - 宽带当月新增量（`SK_KD_MNEW_CNT`）
  - 宽带新增月环比（`SK_KD_MNEW_CNT_HB`）
  - 宽带活跃率（当月流量大于100M）（`SK_KD_MNEW_HYL1`）
  - 宽带较上月底净增数（`SK_KD_MJZ_CNT_SYD`）
  - 宽带较上月底净增环比（`SK_KD_MJZ_CNT_SYD_HB`）
  - 当月工单竣工率（`SK_BYJG_ORDER_JGL`）
  - 当月工单量（`SK_BY_ORDER_CNTS`）
  - 当月流量大于100M的宽带数（`SK_KD_QM_HYCNT1`）
  - 当月竣工工单量（`SK_BYJG_ORDER_CNTS`）
  - 当月累计新增中号卡融合客户（`SK_KD_MNEW_HKRH_CNT`）
  - 新增1000M及以上宽带占比（`SK_KD_MNEW1000_CNT_ZB`）
  - 新增1000M及以上宽带数（`SK_KD_MNEW1000_CNT`）
  - 新增100-200M宽带占比（`SK_KD_MNEW100_CNT_ZB`）
  - 新增100-200M宽带数（`SK_KD_MNEW100_CNT`）
  - 新增200-300M宽带占比（`SK_KD_MNEW200_CNT_ZB`）
  - 新增200-300M宽带数（`SK_KD_MNEW200_CNT`）
  - 新增300-500M宽带占比（`SK_KD_MNEW300_CNT_ZB`）
  - 新增300-500M宽带数（`SK_KD_MNEW300_CNT`）
  - 新增500-1000M宽带占比（`SK_KD_MNEW500_CNT_ZB`）
  - 新增500-1000M宽带数（`SK_KD_MNEW500_CNT`）
  - 新增宽带活跃数（`SK_KD_MNEW_HYCNT`）
  - 新增宽带活跃率（`SK_KD_MNEW_HYL`）
  - 月新增占有线宽带（不含校园）新增比（`SK_KD_MNEW_CNT_ZB`）
  - 期末1000M及以上宽带占比（`SK_KD_QM1000_CNT_ZB`）
  - 期末1000M及以上宽带数（`SK_KD_QM1000_CNT`）
  - 期末100-200M宽带占比（`SK_KD_QM100_CNT_ZB`）
  - 期末100-200M宽带数（`SK_KD_QM100_CNT`）
  - 期末200-300M宽带占比（`SK_KD_QM200_CNT_ZB`）
  - 期末200-300M宽带数（`SK_KD_QM200_CNT`）
  - 期末300-500M宽带占比（`SK_KD_QM300_CNT_ZB`）
  - 期末300-500M宽带数（`SK_KD_QM300_CNT`）
  - 期末500-1000M宽带占比（`SK_KD_QM500_CNT_ZB`）
  - 期末500-1000M宽带数（`SK_KD_QM500_CNT`）
  - 期末客户数（`SK_KD_QM_CNT`）
  - 期末客户数环比（`SK_KD_QM_CNT_HB`）
  - 期末宽带中万兆光猫用户（`SK_WZGMKD_QM_CNT`）
  - 期末宽带活跃数（`SK_KD_QM_HYCNT`）
  - 期末宽带活跃率（`SK_KD_QM_HYL`）
  - 端口利用率（`SK_PORTS_LYL`）
  - 端口数（`SK_PORTS_CNT`）

### 场景：维度：ZQ

- **涉及字段**：`ZQ_BYJG_ORDER_CNTS`, `ZQ_BY_ORDER_CNTS`, `ZQ_BZQG_ORDER_JGL`, `ZQ_KD_DNEW_CNT`, `ZQ_KD_MJZ_CNT`, `ZQ_KD_MJZ_CNT_HB`, `ZQ_KD_MJZ_CNT_SYD`, `ZQ_KD_MJZ_CNT_SYD_HB`, `ZQ_KD_MNEW1000_CNT`, `ZQ_KD_MNEW1000_CNT_ZB`, `ZQ_KD_MNEW100_CNT`, `ZQ_KD_MNEW100_CNT_ZB`, `ZQ_KD_MNEW200_CNT`, `ZQ_KD_MNEW200_CNT_ZB`, `ZQ_KD_MNEW300_CNT`, `ZQ_KD_MNEW300_CNT_ZB`, `ZQ_KD_MNEW500_CNT`, `ZQ_KD_MNEW500_CNT_ZB`, `ZQ_KD_MNEW_CNT`, `ZQ_KD_MNEW_CNT_HB`, `ZQ_KD_MNEW_CNT_ZB`, `ZQ_KD_MNEW_HKRH_CNT`, `ZQ_KD_MNEW_HYCNT`, `ZQ_KD_MNEW_HYL`, `ZQ_KD_MNEW_HYL1`, `ZQ_KD_QM1000_CNT`, `ZQ_KD_QM1000_CNT_ZB`, `ZQ_KD_QM100_CNT`, `ZQ_KD_QM100_CNT_ZB`, `ZQ_KD_QM200_CNT`, `ZQ_KD_QM200_CNT_ZB`, `ZQ_KD_QM300_CNT`, `ZQ_KD_QM300_CNT_ZB`, `ZQ_KD_QM500_CNT`, `ZQ_KD_QM500_CNT_ZB`, `ZQ_KD_QM_CNT`, `ZQ_KD_QM_CNT_HB`, `ZQ_KD_QM_HYCNT`, `ZQ_KD_QM_HYCNT1`, `ZQ_KD_QM_HYL`, `ZQ_PORTS_CNT`, `ZQ_PORTS_LYL`, `ZQ_WZGMKD_QM_CNT`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（43 个）**：
  - 政企宽带当日新增量（`ZQ_KD_DNEW_CNT`）
  - 政企宽带当月新增量（`ZQ_KD_MNEW_CNT`）
  - 政企宽带新增月环比（`ZQ_KD_MNEW_CNT_HB`）
  - 政企宽带活跃率（当月流量大于100M）（`ZQ_KD_MNEW_HYL1`）
  - 政企宽带较上月同期净增数（`ZQ_KD_MJZ_CNT`）
  - 政企宽带较上月同期净增环比（`ZQ_KD_MJZ_CNT_HB`）
  - 政企宽带较上月底净增数（`ZQ_KD_MJZ_CNT_SYD`）
  - 政企宽带较上月底净增环比（`ZQ_KD_MJZ_CNT_SYD_HB`）
  - 政企当月工单竣工率（`ZQ_BZQG_ORDER_JGL`）
  - 政企当月工单量（`ZQ_BY_ORDER_CNTS`）
  - 政企当月流量大于100M的宽带数（`ZQ_KD_QM_HYCNT1`）
  - 政企当月竣工工单量（`ZQ_BYJG_ORDER_CNTS`）
  - 政企当月累计新增中号卡融合客户（`ZQ_KD_MNEW_HKRH_CNT`）
  - 政企新增1000M及以上宽带占比（`ZQ_KD_MNEW1000_CNT_ZB`）
  - 政企新增1000M及以上宽带数（`ZQ_KD_MNEW1000_CNT`）
  - 政企新增100-200M宽带占比（`ZQ_KD_MNEW100_CNT_ZB`）
  - 政企新增100-200M宽带数（`ZQ_KD_MNEW100_CNT`）
  - 政企新增200-300M宽带占比（`ZQ_KD_MNEW200_CNT_ZB`）
  - 政企新增200-300M宽带数（`ZQ_KD_MNEW200_CNT`）
  - 政企新增300-500M宽带占比（`ZQ_KD_MNEW300_CNT_ZB`）
  - 政企新增300-500M宽带数（`ZQ_KD_MNEW300_CNT`）
  - 政企新增500-1000M宽带占比（`ZQ_KD_MNEW500_CNT_ZB`）
  - 政企新增500-1000M宽带数（`ZQ_KD_MNEW500_CNT`）
  - 政企新增宽带活跃数（`ZQ_KD_MNEW_HYCNT`）
  - 政企新增宽带活跃率（`ZQ_KD_MNEW_HYL`）
  - 政企月新增占有线宽带（不含校园）新增比（`ZQ_KD_MNEW_CNT_ZB`）
  - 政企期末1000M及以上宽带占比（`ZQ_KD_QM1000_CNT_ZB`）
  - 政企期末1000M及以上宽带数（`ZQ_KD_QM1000_CNT`）
  - 政企期末100-200M宽带占比（`ZQ_KD_QM100_CNT_ZB`）
  - 政企期末100-200M宽带数（`ZQ_KD_QM100_CNT`）
  - 政企期末200-300M宽带占比（`ZQ_KD_QM200_CNT_ZB`）
  - 政企期末200-300M宽带数（`ZQ_KD_QM200_CNT`）
  - 政企期末300-500M宽带占比（`ZQ_KD_QM300_CNT_ZB`）
  - 政企期末300-500M宽带数（`ZQ_KD_QM300_CNT`）
  - 政企期末500-1000M宽带占比（`ZQ_KD_QM500_CNT_ZB`）
  - 政企期末500-1000M宽带数（`ZQ_KD_QM500_CNT`）
  - 政企期末客户数（`ZQ_KD_QM_CNT`）
  - 政企期末客户数环比（`ZQ_KD_QM_CNT_HB`）
  - 政企期末宽带中万兆光猫用户（`ZQ_WZGMKD_QM_CNT`）
  - 政企期末宽带活跃数（`ZQ_KD_QM_HYCNT`）
  - 政企期末宽带活跃率（`ZQ_KD_QM_HYL`）
  - 政企端口利用率（`ZQ_PORTS_LYL`）
  - 政企端口数（`ZQ_PORTS_CNT`）

### 场景：维度：LY

- **涉及字段**：`LY_BYJG_ORDER_CNTS`, `LY_BY_ORDER_CNTS`, `LY_BZQG_ORDER_JGL`, `LY_KD_DNEW_CNT`, `LY_KD_MJZ_CNT`, `LY_KD_MJZ_CNT_HB`, `LY_KD_MJZ_CNT_SYD`, `LY_KD_MJZ_CNT_SYD_HB`, `LY_KD_MNEW1000_CNT`, `LY_KD_MNEW1000_CNT_ZB`, `LY_KD_MNEW100_CNT`, `LY_KD_MNEW100_CNT_ZB`, `LY_KD_MNEW200_CNT`, `LY_KD_MNEW200_CNT_ZB`, `LY_KD_MNEW300_CNT`, `LY_KD_MNEW300_CNT_ZB`, `LY_KD_MNEW500_CNT`, `LY_KD_MNEW500_CNT_ZB`, `LY_KD_MNEW_CNT`, `LY_KD_MNEW_CNT_HB`, `LY_KD_MNEW_CNT_ZB`, `LY_KD_MNEW_HKRH_CNT`, `LY_KD_MNEW_HYCNT`, `LY_KD_MNEW_HYL`, `LY_KD_MNEW_HYL1`, `LY_KD_QM1000_CNT`, `LY_KD_QM1000_CNT_ZB`, `LY_KD_QM100_CNT`, `LY_KD_QM100_CNT_ZB`, `LY_KD_QM200_CNT`, `LY_KD_QM200_CNT_ZB`, `LY_KD_QM300_CNT`, `LY_KD_QM300_CNT_ZB`, `LY_KD_QM500_CNT`, `LY_KD_QM500_CNT_ZB`, `LY_KD_QM_CNT`, `LY_KD_QM_CNT_HB`, `LY_KD_QM_HYCNT`, `LY_KD_QM_HYCNT1`, `LY_KD_QM_HYL`, `LY_PORTS_CNT`, `LY_PORTS_LYL`, `LY_WZGMKD_QM_CNT`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（43 个）**：
  - 楼园宽带当日新增量（`LY_KD_DNEW_CNT`）
  - 楼园宽带当月新增量（`LY_KD_MNEW_CNT`）
  - 楼园宽带新增月环比（`LY_KD_MNEW_CNT_HB`）
  - 楼园宽带活跃率（当月流量大于100M）（`LY_KD_MNEW_HYL1`）
  - 楼园宽带较上月同期净增数（`LY_KD_MJZ_CNT`）
  - 楼园宽带较上月同期净增环比（`LY_KD_MJZ_CNT_HB`）
  - 楼园当月工单竣工率（`LY_BZQG_ORDER_JGL`）
  - 楼园当月工单量（`LY_BY_ORDER_CNTS`）
  - 楼园当月流量大于100M的宽带数（`LY_KD_QM_HYCNT1`）
  - 楼园当月竣工工单量（`LY_BYJG_ORDER_CNTS`）
  - 楼园当月累计新增中号卡融合客户（`LY_KD_MNEW_HKRH_CNT`）
  - 楼园新增1000M及以上宽带占比（`LY_KD_MNEW1000_CNT_ZB`）
  - 楼园新增1000M及以上宽带数（`LY_KD_MNEW1000_CNT`）
  - 楼园新增100-200M宽带占比（`LY_KD_MNEW100_CNT_ZB`）
  - 楼园新增100-200M宽带数（`LY_KD_MNEW100_CNT`）
  - 楼园新增200-300M宽带占比（`LY_KD_MNEW200_CNT_ZB`）
  - 楼园新增200-300M宽带数（`LY_KD_MNEW200_CNT`）
  - 楼园新增300-500M宽带占比（`LY_KD_MNEW300_CNT_ZB`）
  - 楼园新增300-500M宽带数（`LY_KD_MNEW300_CNT`）
  - 楼园新增500-1000M宽带占比（`LY_KD_MNEW500_CNT_ZB`）
  - 楼园新增500-1000M宽带数（`LY_KD_MNEW500_CNT`）
  - 楼园新增宽带活跃数（`LY_KD_MNEW_HYCNT`）
  - 楼园新增宽带活跃率（`LY_KD_MNEW_HYL`）
  - 楼园月新增占有线宽带（不含校园）新增比（`LY_KD_MNEW_CNT_ZB`）
  - 楼园期末1000M及以上宽带占比（`LY_KD_QM1000_CNT_ZB`）
  - 楼园期末1000M及以上宽带数（`LY_KD_QM1000_CNT`）
  - 楼园期末100-200M宽带占比（`LY_KD_QM100_CNT_ZB`）
  - 楼园期末100-200M宽带数（`LY_KD_QM100_CNT`）
  - 楼园期末200-300M宽带占比（`LY_KD_QM200_CNT_ZB`）
  - 楼园期末200-300M宽带数（`LY_KD_QM200_CNT`）
  - 楼园期末300-500M宽带占比（`LY_KD_QM300_CNT_ZB`）
  - 楼园期末300-500M宽带数（`LY_KD_QM300_CNT`）
  - 楼园期末500-1000M宽带占比（`LY_KD_QM500_CNT_ZB`）
  - 楼园期末500-1000M宽带数（`LY_KD_QM500_CNT`）
  - 楼园期末客户数（`LY_KD_QM_CNT`）
  - 楼园期末客户数环比（`LY_KD_QM_CNT_HB`）
  - 楼园期末宽带中万兆光猫用户（`LY_WZGMKD_QM_CNT`）
  - 楼园期末宽带活跃数（`LY_KD_QM_HYCNT`）
  - 楼园期末宽带活跃率（`LY_KD_QM_HYL`）
  - 楼园端口利用率（`LY_PORTS_LYL`）
  - 楼园端口数（`LY_PORTS_CNT`）
  - 楼园较上月底净增环比（`LY_KD_MJZ_CNT_SYD_HB`）
  - 楼园较上月底净增量（`LY_KD_MJZ_CNT_SYD`）

### 场景：维度：YJ

- **涉及字段**：`YJ_BYJG_ORDER_CNTS`, `YJ_BYJG_ORDER_JGL`, `YJ_BY_ORDER_CNTS`, `YJ_KD_DNEW_CNT`, `YJ_KD_MJZ_CNT`, `YJ_KD_MJZ_CNT_HB`, `YJ_KD_MJZ_CNT_SYD`, `YJ_KD_MJZ_CNT_SYD_HB`, `YJ_KD_MNEW1000_CNT`, `YJ_KD_MNEW1000_CNT_ZB`, `YJ_KD_MNEW100_CNT`, `YJ_KD_MNEW100_CNT_ZB`, `YJ_KD_MNEW200_CNT`, `YJ_KD_MNEW200_CNT_ZB`, `YJ_KD_MNEW300_CNT`, `YJ_KD_MNEW300_CNT_ZB`, `YJ_KD_MNEW500_CNT`, `YJ_KD_MNEW500_CNT_ZB`, `YJ_KD_MNEW_CNT`, `YJ_KD_MNEW_CNT_HB`, `YJ_KD_MNEW_CNT_ZB`, `YJ_KD_MNEW_HKRH_CNT`, `YJ_KD_MNEW_HYCNT`, `YJ_KD_MNEW_HYL`, `YJ_KD_MNEW_HYL1`, `YJ_KD_QM1000_CNT`, `YJ_KD_QM1000_CNT_ZB`, `YJ_KD_QM100_CNT`, `YJ_KD_QM100_CNT_ZB`, `YJ_KD_QM200_CNT`, `YJ_KD_QM200_CNT_ZB`, `YJ_KD_QM300_CNT`, `YJ_KD_QM300_CNT_ZB`, `YJ_KD_QM500_CNT`, `YJ_KD_QM500_CNT_ZB`, `YJ_KD_QM_CNT`, `YJ_KD_QM_CNT_HB`, `YJ_KD_QM_HYCNT`, `YJ_KD_QM_HYCNT1`, `YJ_KD_QM_HYL`, `YJ_PORTS_CNT`, `YJ_PORTS_LYL`, `YJ_WZGMKD_QM_CNT`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（43 个）**：
  - 沿街宽带当日新增量（`YJ_KD_DNEW_CNT`）
  - 沿街宽带当月新增量（`YJ_KD_MNEW_CNT`）
  - 沿街宽带新增月环比（`YJ_KD_MNEW_CNT_HB`）
  - 沿街宽带活跃率（当月流量大于100M）（`YJ_KD_MNEW_HYL1`）
  - 沿街宽带较上月同期净增数（`YJ_KD_MJZ_CNT`）
  - 沿街宽带较上月同期净增环比（`YJ_KD_MJZ_CNT_HB`）
  - 沿街宽带较上月底净增数（`YJ_KD_MJZ_CNT_SYD`）
  - 沿街宽带较上月底净增环比（`YJ_KD_MJZ_CNT_SYD_HB`）
  - 沿街当月工单竣工率（`YJ_BYJG_ORDER_JGL`）
  - 沿街当月工单量（`YJ_BY_ORDER_CNTS`）
  - 沿街当月流量大于100M的宽带数（`YJ_KD_QM_HYCNT1`）
  - 沿街当月竣工工单量（`YJ_BYJG_ORDER_CNTS`）
  - 沿街当月累计新增中号卡融合客户（`YJ_KD_MNEW_HKRH_CNT`）
  - 沿街新增1000M及以上宽带占比（`YJ_KD_MNEW1000_CNT_ZB`）
  - 沿街新增1000M及以上宽带数（`YJ_KD_MNEW1000_CNT`）
  - 沿街新增100-200M宽带占比（`YJ_KD_MNEW100_CNT_ZB`）
  - 沿街新增100-200M宽带数（`YJ_KD_MNEW100_CNT`）
  - 沿街新增200-300M宽带占比（`YJ_KD_MNEW200_CNT_ZB`）
  - 沿街新增200-300M宽带数（`YJ_KD_MNEW200_CNT`）
  - 沿街新增300-500M宽带占比（`YJ_KD_MNEW300_CNT_ZB`）
  - 沿街新增300-500M宽带数（`YJ_KD_MNEW300_CNT`）
  - 沿街新增500-1000M宽带占比（`YJ_KD_MNEW500_CNT_ZB`）
  - 沿街新增500-1000M宽带数（`YJ_KD_MNEW500_CNT`）
  - 沿街新增宽带活跃数（`YJ_KD_MNEW_HYCNT`）
  - 沿街新增宽带活跃率（`YJ_KD_MNEW_HYL`）
  - 沿街月新增占有线宽带（不含校园）新增比（`YJ_KD_MNEW_CNT_ZB`）
  - 沿街期末1000M及以上宽带占比（`YJ_KD_QM1000_CNT_ZB`）
  - 沿街期末1000M及以上宽带数（`YJ_KD_QM1000_CNT`）
  - 沿街期末100-200M宽带占比（`YJ_KD_QM100_CNT_ZB`）
  - 沿街期末100-200M宽带数（`YJ_KD_QM100_CNT`）
  - 沿街期末200-300M宽带占比（`YJ_KD_QM200_CNT_ZB`）
  - 沿街期末200-300M宽带数（`YJ_KD_QM200_CNT`）
  - 沿街期末300-500M宽带占比（`YJ_KD_QM300_CNT_ZB`）
  - 沿街期末300-500M宽带数（`YJ_KD_QM300_CNT`）
  - 沿街期末500-1000M宽带占比（`YJ_KD_QM500_CNT_ZB`）
  - 沿街期末500-1000M宽带数（`YJ_KD_QM500_CNT`）
  - 沿街期末客户数（`YJ_KD_QM_CNT`）
  - 沿街期末客户数环比（`YJ_KD_QM_CNT_HB`）
  - 沿街期末宽带中万兆光猫用户（`YJ_WZGMKD_QM_CNT`）
  - 沿街期末宽带活跃数（`YJ_KD_QM_HYCNT`）
  - 沿街期末宽带活跃率（`YJ_KD_QM_HYL`）
  - 沿街端口利用率（`YJ_PORTS_LYL`）
  - 沿街端口数（`YJ_PORTS_CNT`）

### 场景：维度：FZS

- **涉及字段**：`FZS_BYJG_ORDER_CNTS`, `FZS_BY_ORDER_CNTS`, `FZS_BZQG_ORDER_JGL`, `FZS_KD_DNEW_CNT`, `FZS_KD_MJZ_CNT`, `FZS_KD_MJZ_CNT_HB`, `FZS_KD_MJZ_CNT_SYD`, `FZS_KD_MJZ_CNT_SYD_HB`, `FZS_KD_MNEW1000_CNT`, `FZS_KD_MNEW1000_CNT_ZB`, `FZS_KD_MNEW100_CNT`, `FZS_KD_MNEW100_CNT_ZB`, `FZS_KD_MNEW200_CNT`, `FZS_KD_MNEW200_CNT_ZB`, `FZS_KD_MNEW300_CNT`, `FZS_KD_MNEW300_CNT_ZB`, `FZS_KD_MNEW500_CNT`, `FZS_KD_MNEW500_CNT_ZB`, `FZS_KD_MNEW_CNT`, `FZS_KD_MNEW_CNT_HB`, `FZS_KD_MNEW_CNT_ZB`, `FZS_KD_MNEW_HKRH_CNT`, `FZS_KD_MNEW_HYCNT`, `FZS_KD_MNEW_HYL`, `FZS_KD_MNEW_HYL1`, `FZS_KD_QM1000_CNT`, `FZS_KD_QM1000_CNT_ZB`, `FZS_KD_QM100_CNT`, `FZS_KD_QM100_CNT_ZB`, `FZS_KD_QM200_CNT`, `FZS_KD_QM200_CNT_ZB`, `FZS_KD_QM300_CNT`, `FZS_KD_QM300_CNT_ZB`, `FZS_KD_QM500_CNT`, `FZS_KD_QM500_CNT_ZB`, `FZS_KD_QM_CNT`, `FZS_KD_QM_CNT_HB`, `FZS_KD_QM_HYCNT`, `FZS_KD_QM_HYCNT1`, `FZS_KD_QM_HYL`, `FZS_PORTS_CNT`, `FZS_PORTS_LYL`, `FZS_WZGMKD_QM_CNT`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（43 个）**：
  - 泛住宿宽带当日新增量（`FZS_KD_DNEW_CNT`）
  - 泛住宿宽带当月新增量（`FZS_KD_MNEW_CNT`）
  - 泛住宿宽带新增月环比（`FZS_KD_MNEW_CNT_HB`）
  - 泛住宿宽带活跃率（当月流量大于100M）（`FZS_KD_MNEW_HYL1`）
  - 泛住宿宽带较上月同期净增数（`FZS_KD_MJZ_CNT`）
  - 泛住宿宽带较上月同期净增环比（`FZS_KD_MJZ_CNT_HB`）
  - 泛住宿宽带较上月底净增环比（`FZS_KD_MJZ_CNT_SYD_HB`）
  - 泛住宿宽带较上月底净增量（`FZS_KD_MJZ_CNT_SYD`）
  - 泛住宿当月工单竣工率（`FZS_BZQG_ORDER_JGL`）
  - 泛住宿当月工单量（`FZS_BY_ORDER_CNTS`）
  - 泛住宿当月流量大于100M的宽带数（`FZS_KD_QM_HYCNT1`）
  - 泛住宿当月竣工工单量（`FZS_BYJG_ORDER_CNTS`）
  - 泛住宿当月累计新增中号卡融合客户（`FZS_KD_MNEW_HKRH_CNT`）
  - 泛住宿新增1000M及以上宽带占比（`FZS_KD_MNEW1000_CNT_ZB`）
  - 泛住宿新增1000M及以上宽带数（`FZS_KD_MNEW1000_CNT`）
  - 泛住宿新增100-200M宽带占比（`FZS_KD_MNEW100_CNT_ZB`）
  - 泛住宿新增100-200M宽带数（`FZS_KD_MNEW100_CNT`）
  - 泛住宿新增200-300M宽带占比（`FZS_KD_MNEW200_CNT_ZB`）
  - 泛住宿新增200-300M宽带数（`FZS_KD_MNEW200_CNT`）
  - 泛住宿新增300-500M宽带占比（`FZS_KD_MNEW300_CNT_ZB`）
  - 泛住宿新增300-500M宽带数（`FZS_KD_MNEW300_CNT`）
  - 泛住宿新增500-1000M宽带占比（`FZS_KD_MNEW500_CNT_ZB`）
  - 泛住宿新增500-1000M宽带数（`FZS_KD_MNEW500_CNT`）
  - 泛住宿新增宽带活跃数（`FZS_KD_MNEW_HYCNT`）
  - 泛住宿新增宽带活跃率（`FZS_KD_MNEW_HYL`）
  - 泛住宿月新增占有线宽带（不含校园）新增比（`FZS_KD_MNEW_CNT_ZB`）
  - 泛住宿期末1000M及以上宽带占比（`FZS_KD_QM1000_CNT_ZB`）
  - 泛住宿期末1000M及以上宽带数（`FZS_KD_QM1000_CNT`）
  - 泛住宿期末100-200M宽带占比（`FZS_KD_QM100_CNT_ZB`）
  - 泛住宿期末100-200M宽带数（`FZS_KD_QM100_CNT`）
  - 泛住宿期末200-300M宽带占比（`FZS_KD_QM200_CNT_ZB`）
  - 泛住宿期末200-300M宽带数（`FZS_KD_QM200_CNT`）
  - 泛住宿期末300-500M宽带占比（`FZS_KD_QM300_CNT_ZB`）
  - 泛住宿期末300-500M宽带数（`FZS_KD_QM300_CNT`）
  - 泛住宿期末500-1000M宽带占比（`FZS_KD_QM500_CNT_ZB`）
  - 泛住宿期末500-1000M宽带数（`FZS_KD_QM500_CNT`）
  - 泛住宿期末客户数（`FZS_KD_QM_CNT`）
  - 泛住宿期末客户数环比（`FZS_KD_QM_CNT_HB`）
  - 泛住宿期末宽带中万兆光猫用户（`FZS_WZGMKD_QM_CNT`）
  - 泛住宿期末宽带活跃数（`FZS_KD_QM_HYCNT`）
  - 泛住宿期末宽带活跃率（`FZS_KD_QM_HYL`）
  - 泛住宿端口利用率（`FZS_PORTS_LYL`）
  - 泛住宿端口数（`FZS_PORTS_CNT`）

### 场景：维度：ZQKD

- **涉及字段**：`ZQKD_CLHK_MNEW_CNT`, `ZQKD_XZHK_MNEW_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（2 个）**：
  - 政企新增来源-存量号卡（`ZQKD_CLHK_MNEW_CNT`）
  - 政企新增来源-新增号卡（`ZQKD_XZHK_MNEW_CNT`）

### 场景：维度：SKKD

- **涉及字段**：`SKKD_CLHK_MNEW_CNT`, `SKKD_XZHK_MNEW_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（2 个）**：
  - 新增来源-存量号卡（`SKKD_CLHK_MNEW_CNT`）
  - 新增来源-新增号卡（`SKKD_XZHK_MNEW_CNT`）

### 场景：维度：LYKD

- **涉及字段**：`LYKD_CLHK_MNEW_CNT`, `LYKD_XZHK_MNEW_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（2 个）**：
  - 楼园新增来源-存量号卡（`LYKD_CLHK_MNEW_CNT`）
  - 楼园新增来源-新增号卡（`LYKD_XZHK_MNEW_CNT`）

### 场景：维度：YJKD

- **涉及字段**：`YJKD_CLHK_MNEW_CNT`, `YJKD_XZHK_MNEW_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（2 个）**：
  - 沿街新增来源-存量号卡（`YJKD_CLHK_MNEW_CNT`）
  - 沿街新增来源-新增号卡（`YJKD_XZHK_MNEW_CNT`）

### 场景：维度：FZSKD

- **涉及字段**：`FZSKD_CLHK_MNEW_CNT`, `FZSKD_XZHK_MNEW_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（2 个）**：
  - 泛住宿新增来源-存量号卡（`FZSKD_CLHK_MNEW_CNT`）
  - 泛住宿新增来源-新增号卡（`FZSKD_XZHK_MNEW_CNT`）

### 场景：维度：SK10GPON

- **涉及字段**：`SK10GPON_PORTS_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 其中10Gpon端口数（`SK10GPON_PORTS_CNT`）

### 场景：维度：ZQ10GPON

- **涉及字段**：`ZQ10GPON_PORTS_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 政企其中10Gpon端口数（`ZQ10GPON_PORTS_CNT`）

### 场景：维度：NXYKD

- **涉及字段**：`NXYKD_MNEW_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 新增有线宽带量（`NXYKD_MNEW_CNT`）

### 场景：维度：LY10GPON

- **涉及字段**：`LY10GPON_PORTS_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 楼园其中10Gpon端口数（`LY10GPON_PORTS_CNT`）

### 场景：维度：YJ10GPON

- **涉及字段**：`YJ10GPON_PORTS_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 沿街其中10Gpon端口数（`YJ10GPON_PORTS_CNT`）

### 场景：维度：FZS10GPON

- **涉及字段**：`FZS10GPON_PORTS_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 泛住宿其中10Gpon端口数（`FZS10GPON_PORTS_CNT`）

## TB_KR_GRP_SK_OPPO_TOL_RH_DAY（共 110 个指标）

### 场景：OPPO_TYPE='8'

- **涉及字段**：`COMPLETED_OPPO_D_CNT`, `FAIL_OPPO_D_CNT`, `GRAB_OPPO_D_CNT`, `INUSE_OPPO_D_CNT`, `NOUSE_OPPO_D_CNT`, `OPPO_D_CNT`, `SUCCESS_OPPO_D_CNT`, `SUCCESS_OPPO_D_RATE`, `USE_OPPO_D_RATE`, `VERIFY_OPPO_D_CNT`, `WX_OPPO_D_CNT`
- **分类编码**：8
- **单位**：%, -
- **可产出的指标（11 个）**：
  - 一楼一码商机处理率（`USE_OPPO_D_RATE`）
  - 一楼一码商机数（`OPPO_D_CNT`）
  - 一楼一码商机转化率（`SUCCESS_OPPO_D_RATE`）
  - 一楼一码在途商机数（`INUSE_OPPO_D_CNT`）
  - 一楼一码已关闭商机数（`WX_OPPO_D_CNT`）
  - 一楼一码已办结商机数（`COMPLETED_OPPO_D_CNT`）
  - 一楼一码已成功商机数（`SUCCESS_OPPO_D_CNT`）
  - 一楼一码已过期商机数（`FAIL_OPPO_D_CNT`）
  - 一楼一码待抢单商机数（`GRAB_OPPO_D_CNT`）
  - 一楼一码待核实商机数（`VERIFY_OPPO_D_CNT`）
  - 一楼一码无法办理商机数（`NOUSE_OPPO_D_CNT`）

### 场景：OPPO_TYPE='5'

- **涉及字段**：`COMPLETED_OPPO_D_CNT`, `FAIL_OPPO_D_CNT`, `GRAB_OPPO_D_CNT`, `INUSE_OPPO_D_CNT`, `NOUSE_OPPO_D_CNT`, `OPPO_D_CNT`, `SUCCESS_OPPO_D_CNT`, `SUCCESS_OPPO_D_RATE`, `USE_OPPO_D_RATE`, `VERIFY_OPPO_D_CNT`, `WX_OPPO_D_CNT`
- **分类编码**：8
- **单位**：%, -
- **可产出的指标（11 个）**：
  - 人工录入商机处理率（`USE_OPPO_D_RATE`）
  - 人工录入商机数（`OPPO_D_CNT`）
  - 人工录入商机转化率（`SUCCESS_OPPO_D_RATE`）
  - 人工录入在途商机数（`INUSE_OPPO_D_CNT`）
  - 人工录入已关闭商机数（`WX_OPPO_D_CNT`）
  - 人工录入已办结商机数（`COMPLETED_OPPO_D_CNT`）
  - 人工录入已成功商机数（`SUCCESS_OPPO_D_CNT`）
  - 人工录入已过期商机数（`FAIL_OPPO_D_CNT`）
  - 人工录入待抢单商机数（`GRAB_OPPO_D_CNT`）
  - 人工录入待核实商机数（`VERIFY_OPPO_D_CNT`）
  - 人工录入无法办理商机数（`NOUSE_OPPO_D_CNT`）

### 场景：OPPO_TYPE='91'

- **涉及字段**：`COMPLETED_OPPO_D_CNT`, `FAIL_OPPO_D_CNT`, `GRAB_OPPO_D_CNT`, `INUSE_OPPO_D_CNT`, `NOUSE_OPPO_D_CNT`, `OPPO_D_CNT`, `SUCCESS_OPPO_D_CNT`, `SUCCESS_OPPO_D_RATE`, `USE_OPPO_D_RATE`, `VERIFY_OPPO_D_CNT`, `WX_OPPO_D_CNT`
- **分类编码**：8
- **单位**：%, -
- **可产出的指标（11 个）**：
  - 商机处理率（`USE_OPPO_D_RATE`）
  - 商机数（`OPPO_D_CNT`）
  - 商机转化率（`SUCCESS_OPPO_D_RATE`）
  - 在途商机数（`INUSE_OPPO_D_CNT`）
  - 已关闭商机数（`WX_OPPO_D_CNT`）
  - 已办结商机数（`COMPLETED_OPPO_D_CNT`）
  - 已成功商机数（`SUCCESS_OPPO_D_CNT`）
  - 已过期商机数（`FAIL_OPPO_D_CNT`）
  - 待抢单商机数（`GRAB_OPPO_D_CNT`）
  - 待核实商机数（`VERIFY_OPPO_D_CNT`）
  - 无法办理商机数（`NOUSE_OPPO_D_CNT`）

### 场景：OPPO_TYPE='93'

- **涉及字段**：`COMPLETED_OPPO_D_CNT`, `FAIL_OPPO_D_CNT`, `GRAB_OPPO_D_CNT`, `INUSE_OPPO_D_CNT`, `NOUSE_OPPO_D_CNT`, `OPPO_D_CNT`, `SUCCESS_OPPO_D_CNT`, `SUCCESS_OPPO_D_RATE`, `USE_OPPO_D_RATE`, `VERIFY_OPPO_D_CNT`, `WX_OPPO_D_CNT`
- **分类编码**：8
- **单位**：%, -
- **可产出的指标（11 个）**：
  - 客户找我商机处理率（`USE_OPPO_D_RATE`）
  - 客户找我商机数（`OPPO_D_CNT`）
  - 客户找我商机转化率（`SUCCESS_OPPO_D_RATE`）
  - 客户找我在途商机数（`INUSE_OPPO_D_CNT`）
  - 客户找我已关闭商机数（`WX_OPPO_D_CNT`）
  - 客户找我已办结商机数（`COMPLETED_OPPO_D_CNT`）
  - 客户找我已成功商机数（`SUCCESS_OPPO_D_CNT`）
  - 客户找我已过期商机数（`FAIL_OPPO_D_CNT`）
  - 客户找我待抢单商机数（`GRAB_OPPO_D_CNT`）
  - 客户找我待核实商机数（`VERIFY_OPPO_D_CNT`）
  - 客户找我无法办理商机数（`NOUSE_OPPO_D_CNT`）

### 场景：OPPO_TYPE='94'

- **涉及字段**：`COMPLETED_OPPO_D_CNT`, `FAIL_OPPO_D_CNT`, `GRAB_OPPO_D_CNT`, `INUSE_OPPO_D_CNT`, `NOUSE_OPPO_D_CNT`, `OPPO_D_CNT`, `SUCCESS_OPPO_D_CNT`, `SUCCESS_OPPO_D_RATE`, `USE_OPPO_D_RATE`, `VERIFY_OPPO_D_CNT`, `WX_OPPO_D_CNT`
- **分类编码**：8
- **单位**：%, -
- **可产出的指标（11 个）**：
  - 我找客户商机处理率（`USE_OPPO_D_RATE`）
  - 我找客户商机数（`OPPO_D_CNT`）
  - 我找客户商机转化率（`SUCCESS_OPPO_D_RATE`）
  - 我找客户在途商机数（`INUSE_OPPO_D_CNT`）
  - 我找客户已关闭商机数（`WX_OPPO_D_CNT`）
  - 我找客户已办结商机数（`COMPLETED_OPPO_D_CNT`）
  - 我找客户已成功商机数（`SUCCESS_OPPO_D_CNT`）
  - 我找客户已过期商机数（`FAIL_OPPO_D_CNT`）
  - 我找客户待抢单商机数（`GRAB_OPPO_D_CNT`）
  - 我找客户待核实商机数（`VERIFY_OPPO_D_CNT`）
  - 我找客户无法办理商机数（`NOUSE_OPPO_D_CNT`）

### 场景：OPPO_TYPE='13'

- **涉及字段**：`COMPLETED_OPPO_D_CNT`, `FAIL_OPPO_D_CNT`, `GRAB_OPPO_D_CNT`, `INUSE_OPPO_D_CNT`, `NOUSE_OPPO_D_CNT`, `OPPO_D_CNT`, `SUCCESS_OPPO_D_CNT`, `SUCCESS_OPPO_D_RATE`, `USE_OPPO_D_RATE`, `VERIFY_OPPO_D_CNT`, `WX_OPPO_D_CNT`
- **分类编码**：8
- **单位**：%, -
- **可产出的指标（11 个）**：
  - 手厅预约商机处理率（`USE_OPPO_D_RATE`）
  - 手厅预约商机数（`OPPO_D_CNT`）
  - 手厅预约商机转化率（`SUCCESS_OPPO_D_RATE`）
  - 手厅预约在途商机数（`INUSE_OPPO_D_CNT`）
  - 手厅预约已关闭商机数（`WX_OPPO_D_CNT`）
  - 手厅预约已办结商机数（`COMPLETED_OPPO_D_CNT`）
  - 手厅预约已成功商机数（`SUCCESS_OPPO_D_CNT`）
  - 手厅预约已过期商机数（`FAIL_OPPO_D_CNT`）
  - 手厅预约待抢单商机数（`GRAB_OPPO_D_CNT`）
  - 手厅预约待核实商机数（`VERIFY_OPPO_D_CNT`）
  - 手厅预约无法办理商机数（`NOUSE_OPPO_D_CNT`）

### 场景：OPPO_TYPE='9'

- **涉及字段**：`COMPLETED_OPPO_D_CNT`, `FAIL_OPPO_D_CNT`, `GRAB_OPPO_D_CNT`, `INUSE_OPPO_D_CNT`, `NOUSE_OPPO_D_CNT`, `OPPO_D_CNT`, `SUCCESS_OPPO_D_CNT`, `SUCCESS_OPPO_D_RATE`, `USE_OPPO_D_RATE`, `VERIFY_OPPO_D_CNT`, `WX_OPPO_D_CNT`
- **分类编码**：8
- **单位**：%, -
- **可产出的指标（11 个）**：
  - 批量导入商机处理率（`USE_OPPO_D_RATE`）
  - 批量导入商机数（`OPPO_D_CNT`）
  - 批量导入商机转化率（`SUCCESS_OPPO_D_RATE`）
  - 批量导入在途商机数（`INUSE_OPPO_D_CNT`）
  - 批量导入已关闭商机数（`WX_OPPO_D_CNT`）
  - 批量导入已办结商机数（`COMPLETED_OPPO_D_CNT`）
  - 批量导入已成功商机数（`SUCCESS_OPPO_D_CNT`）
  - 批量导入已过期商机数（`FAIL_OPPO_D_CNT`）
  - 批量导入待抢单商机数（`GRAB_OPPO_D_CNT`）
  - 批量导入待核实商机数（`VERIFY_OPPO_D_CNT`）
  - 批量导入无法办理商机数（`NOUSE_OPPO_D_CNT`）

### 场景：OPPO_TYPE='3'

- **涉及字段**：`COMPLETED_OPPO_D_CNT`, `FAIL_OPPO_D_CNT`, `GRAB_OPPO_D_CNT`, `INUSE_OPPO_D_CNT`, `NOUSE_OPPO_D_CNT`, `OPPO_D_CNT`, `SUCCESS_OPPO_D_CNT`, `SUCCESS_OPPO_D_RATE`, `USE_OPPO_D_RATE`, `VERIFY_OPPO_D_CNT`, `WX_OPPO_D_CNT`
- **分类编码**：8
- **单位**：%, -
- **可产出的指标（11 个）**：
  - 新开商铺商机处理率（`USE_OPPO_D_RATE`）
  - 新开商铺商机数（`OPPO_D_CNT`）
  - 新开商铺商机转化率（`SUCCESS_OPPO_D_RATE`）
  - 新开商铺在途商机数（`INUSE_OPPO_D_CNT`）
  - 新开商铺已关闭商机数（`WX_OPPO_D_CNT`）
  - 新开商铺已办结商机数（`COMPLETED_OPPO_D_CNT`）
  - 新开商铺已成功商机数（`SUCCESS_OPPO_D_CNT`）
  - 新开商铺已过期商机数（`FAIL_OPPO_D_CNT`）
  - 新开商铺待抢单商机数（`GRAB_OPPO_D_CNT`）
  - 新开商铺待核实商机数（`VERIFY_OPPO_D_CNT`）
  - 新开商铺无法办理商机数（`NOUSE_OPPO_D_CNT`）

### 场景：OPPO_TYPE='11'

- **涉及字段**：`COMPLETED_OPPO_D_CNT`, `FAIL_OPPO_D_CNT`, `GRAB_OPPO_D_CNT`, `INUSE_OPPO_D_CNT`, `NOUSE_OPPO_D_CNT`, `OPPO_D_CNT`, `SUCCESS_OPPO_D_CNT`, `SUCCESS_OPPO_D_RATE`, `USE_OPPO_D_RATE`, `VERIFY_OPPO_D_CNT`, `WX_OPPO_D_CNT`
- **分类编码**：8
- **单位**：%, -
- **可产出的指标（11 个）**：
  - 热线商机处理率（`USE_OPPO_D_RATE`）
  - 热线商机数（`OPPO_D_CNT`）
  - 热线商机转化率（`SUCCESS_OPPO_D_RATE`）
  - 热线在途商机数（`INUSE_OPPO_D_CNT`）
  - 热线已关闭商机数（`WX_OPPO_D_CNT`）
  - 热线已办结商机数（`COMPLETED_OPPO_D_CNT`）
  - 热线已成功商机数（`SUCCESS_OPPO_D_CNT`）
  - 热线已过期商机数（`FAIL_OPPO_D_CNT`）
  - 热线待抢单商机数（`GRAB_OPPO_D_CNT`）
  - 热线待核实商机数（`VERIFY_OPPO_D_CNT`）
  - 热线无法办理商机数（`NOUSE_OPPO_D_CNT`）

### 场景：OPPO_TYPE='12'

- **涉及字段**：`COMPLETED_OPPO_D_CNT`, `FAIL_OPPO_D_CNT`, `GRAB_OPPO_D_CNT`, `INUSE_OPPO_D_CNT`, `NOUSE_OPPO_D_CNT`, `OPPO_D_CNT`, `SUCCESS_OPPO_D_CNT`, `SUCCESS_OPPO_D_RATE`, `USE_OPPO_D_RATE`, `VERIFY_OPPO_D_CNT`, `WX_OPPO_D_CNT`
- **分类编码**：8
- **单位**：%, -
- **可产出的指标（11 个）**：
  - 随手拍商机处理率（`USE_OPPO_D_RATE`）
  - 随手拍商机数（`OPPO_D_CNT`）
  - 随手拍商机转化率（`SUCCESS_OPPO_D_RATE`）
  - 随手拍在途商机数（`INUSE_OPPO_D_CNT`）
  - 随手拍已关闭商机数（`WX_OPPO_D_CNT`）
  - 随手拍已办结商机数（`COMPLETED_OPPO_D_CNT`）
  - 随手拍已成功商机数（`SUCCESS_OPPO_D_CNT`）
  - 随手拍已过期商机数（`FAIL_OPPO_D_CNT`）
  - 随手拍待抢单商机数（`GRAB_OPPO_D_CNT`）
  - 随手拍待核实商机数（`VERIFY_OPPO_D_CNT`）
  - 随手拍无法办理商机数（`NOUSE_OPPO_D_CNT`）

## TB_KR_GRP_SK_SCENE_SHARES_DAY（共 63 个指标）

### 场景：SCENE_TYPE = 'all'

- **涉及字段**：`DX_KD_CNT_PRE`, `DX_KD_RATE`, `LT_KD_CNT_PRE`, `LT_KD_RATE`, `PACKAGE_AREA_ID`, `PACKAGE_AREA_NAME`, `SCENE_TYPE`, `SCENE_TYPE_NAME`, `STATIS_MONTH`, `TOTAL_KD_CNT_PRE`, `YD_KD_CNT_PRE`, `YD_KD_LM_RATE`, `YD_KD_PP`, `YD_KD_RATE_INX`, `YD_KD_RATIO`, `YW_KD_CNT`, `YW_KD_CNT_PRE`, `YW_KD_RATE`
- **分类编码**：-
- **单位**：%, -, pp
- **可产出的指标（18 个）**：
  - 上月移动宽带份额（`YD_KD_LM_RATE`）
  - 分包区域名称（`PACKAGE_AREA_NAME`）
  - 分包区域编码（`PACKAGE_AREA_ID`）
  - 场景类型名称（`SCENE_TYPE_NAME`）
  - 场景类型编码（`SCENE_TYPE`）
  - 宽带店铺数-上月（`TOTAL_KD_CNT_PRE`）
  - 异网宽带份额（`YW_KD_RATE`）
  - 异网宽带数（`YW_KD_CNT`）
  - 异网宽带数-上月（`YW_KD_CNT_PRE`）
  - 本网环比提升（`YD_KD_PP`）
  - 电信宽带份额（`DX_KD_RATE`）
  - 电信宽带数-上月（`DX_KD_CNT_PRE`）
  - 移动宽带份额排名（`YD_KD_RATE_INX`）
  - 移动宽带份额环比（`YD_KD_RATIO`）
  - 移动宽带数-上月（`YD_KD_CNT_PRE`）
  - 统计月份（`STATIS_MONTH`）
  - 联通宽带份额（`LT_KD_RATE`）
  - 联通宽带数-上月（`LT_KD_CNT_PRE`）

### 场景：SCENE_TYPE='03'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_LY_PP`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -, pp
- **可产出的指标（5 个）**：
  - 专业市场-电信宽带数（`DX_KD_CNT`）
  - 专业市场-移动份额（`YD_KD_RATE`）
  - 专业市场-移动宽带数（`YD_KD_CNT`）
  - 专业市场-联通宽带数（`LT_KD_CNT`）
  - 专业市场-较上年底份额提升（`YD_KD_LY_PP`）

### 场景：SCENE_TYPE='04'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_LY_PP`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -, pp
- **可产出的指标（5 个）**：
  - 产业园区-电信宽带数（`DX_KD_CNT`）
  - 产业园区-移动份额（`YD_KD_RATE`）
  - 产业园区-移动宽带数（`YD_KD_CNT`）
  - 产业园区-联通宽带数（`LT_KD_CNT`）
  - 产业园区-较上年底份额提升（`YD_KD_LY_PP`）

### 场景：SCENE_TYPE='07'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_LY_PP`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -, pp
- **可产出的指标（5 个）**：
  - 公司企业-电信宽带数（`DX_KD_CNT`）
  - 公司企业-移动份额（`YD_KD_RATE`）
  - 公司企业-移动宽带数（`YD_KD_CNT`）
  - 公司企业-联通宽带数（`LT_KD_CNT`）
  - 公司企业-较上年底份额提升（`YD_KD_LY_PP`）

### 场景：SCENE_TYPE='06'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_LY_PP`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -, pp
- **可产出的指标（5 个）**：
  - 商业综合体-电信宽带数（`DX_KD_CNT`）
  - 商业综合体-移动份额（`YD_KD_RATE`）
  - 商业综合体-移动宽带数（`YD_KD_CNT`）
  - 商业综合体-联通宽带数（`LT_KD_CNT`）
  - 商业综合体-较上年底份额提升（`YD_KD_LY_PP`）

### 场景：SCENE_TYPE='01'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_LY_PP`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -, pp
- **可产出的指标（5 个）**：
  - 商务楼宇-电信宽带数（`DX_KD_CNT`）
  - 商务楼宇-移动份额（`YD_KD_RATE`）
  - 商务楼宇-移动宽带数（`YD_KD_CNT`）
  - 商务楼宇-联通宽带数（`LT_KD_CNT`）
  - 商务楼宇-较上年底份额提升（`YD_KD_LY_PP`）

### 场景：SCENE_TYPE='08'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_LY_PP`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -, pp
- **可产出的指标（5 个）**：
  - 楼园-电信宽带数（`DX_KD_CNT`）
  - 楼园-移动份额（`YD_KD_RATE`）
  - 楼园-移动宽带数（`YD_KD_CNT`）
  - 楼园-联通宽带数（`LT_KD_CNT`）
  - 楼园-较上年底份额提升（`YD_KD_LY_PP`）

### 场景：SCENE_TYPE='05'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_LY_PP`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -, pp
- **可产出的指标（5 个）**：
  - 沿街商铺-电信宽带数（`DX_KD_CNT`）
  - 沿街商铺-移动份额（`YD_KD_RATE`）
  - 沿街商铺-移动宽带数（`YD_KD_CNT`）
  - 沿街商铺-联通宽带数（`LT_KD_CNT`）
  - 沿街商铺-较上年底份额提升（`YD_KD_LY_PP`）

### 场景：SCENE_TYPE='02'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_LY_PP`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -, pp
- **可产出的指标（5 个）**：
  - 泛住宿-电信宽带数（`DX_KD_CNT`）
  - 泛住宿-移动份额（`YD_KD_RATE`）
  - 泛住宿-移动宽带数（`YD_KD_CNT`）
  - 泛住宿-联通宽带数（`LT_KD_CNT`）
  - 泛住宿-较上年底提升（`YD_KD_LY_PP`）

### 场景：SCENE_TYPE='all'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_LY_PP`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -, pp
- **可产出的指标（5 个）**：
  - 电信宽带数（`DX_KD_CNT`）
  - 移动宽带份额（`YD_KD_RATE`）
  - 移动宽带数（`YD_KD_CNT`）
  - 联通宽带数（`LT_KD_CNT`）
  - 较上年底份额提升（`YD_KD_LY_PP`）

## TB_KR_GRP_SK_PK_BENCHMARK_DAY（共 40 个指标）

### 场景：INDICATOR_CODE='13' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - e企组网日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='13' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - e企组网月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='9' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - FTTR/FTTO日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='9' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - FTTR/FTTO月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='15' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - ITS日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='15' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - ITS月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='20' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 三大件云电脑日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='20' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 三大件云电脑月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='16' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 专线卫士日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='16' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 专线卫士月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='11' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 专线日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='11' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 专线月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='12' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 企宽日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='12' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 企宽月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='14' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 千里眼日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='14' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 千里眼月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='17' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 和对讲日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='17' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 和对讲月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='4' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 商客价值套餐日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='4' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 商客价值套餐月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='5' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 商客宽带日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='5' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 商客宽带月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='8' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 安防日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='8' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 安防月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='1' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：1
- **单位**：万元
- **可产出的指标（1 个）**：
  - 当日商客收入（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='19' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 当日地图下单量（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='18' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 当日地图建档量（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='3' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：1
- **单位**：万元
- **可产出的指标（1 个）**：
  - 当日基于标品收入（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='2' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：1
- **单位**：万元
- **可产出的指标（1 个）**：
  - 当日基于线收入（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='1' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：1
- **单位**：万元
- **可产出的指标（1 个）**：
  - 当月商客收入（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='19' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 当月地图下单量（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='18' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 当月地图建档量（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='3' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：1
- **单位**：万元
- **可产出的指标（1 个）**：
  - 当月基于标品收入（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='2' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：1
- **单位**：万元
- **可产出的指标（1 个）**：
  - 当月基于线收入（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='6' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 拉新号卡日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='6' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 拉新号卡月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='10' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 政企云电脑日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='10' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 政企云电脑月新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='7' AND DATA_TYPE='1'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 轻SaaS日新增（`INDICATOR_NUM`）

### 场景：INDICATOR_CODE='7' AND DATA_TYPE='2'

- **涉及字段**：`INDICATOR_NUM`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 轻SaaS月新增（`INDICATOR_NUM`）

## TB_KR_GRP_SK_POI_PACK_TOL_DAY（共 39 个指标）

### 场景：维度：PACKAGE

- **涉及字段**：`PACKAGE_AREA_CNT`, `PACKAGE_AREA_HB`, `PACKAGE_AREA_ID`, `PACKAGE_AREA_LM_CNT`, `PACKAGE_AREA_NAME`, `PACKAGE_CNT`, `PACKAGE_CNT_HB`, `PACKAGE_LM_CNT`
- **分类编码**：-, 7
- **单位**：%, -
- **可产出的指标（8 个）**：
  - 上月分包人数量（`PACKAGE_LM_CNT`）
  - 上月底分包区域数（`PACKAGE_AREA_LM_CNT`）
  - 分包人数量（`PACKAGE_CNT`）
  - 分包人数量环比（`PACKAGE_CNT_HB`）
  - 分包区域名称（`PACKAGE_AREA_NAME`）
  - 分包区域数（`PACKAGE_AREA_CNT`）
  - 分包区域数环比（`PACKAGE_AREA_HB`）
  - 分包区域编码（`PACKAGE_AREA_ID`）

### 场景：维度：PACKED

- **涉及字段**：`PACKED_AREA_CNT`, `PACKED_AREA_LM_RATE`, `PACKED_AREA_PP`, `PACKED_AREA_RATE`
- **分类编码**：-, 7
- **单位**：%, -, pp
- **可产出的指标（4 个）**：
  - 上月分包率（`PACKED_AREA_LM_RATE`）
  - 分包率（`PACKED_AREA_RATE`）
  - 分包率环比提升（`PACKED_AREA_PP`）
  - 已分包区域数（`PACKED_AREA_CNT`）

### 场景：维度：YD

- **涉及字段**：`YD_ALLBUILD_DATE`, `YD_ALL_RATE`, `YD_BUILD_RATE`, `YD_POICUST_DATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 商铺及企业份额更新时间（`YD_POICUST_DATE`）
  - 整体份额（`YD_ALL_RATE`）
  - 整体及楼园份额更新时间（`YD_ALLBUILD_DATE`）
  - 楼园份额（`YD_BUILD_RATE`）

### 场景：维度：PRE

- **涉及字段**：`PRE_FREE_PORTS_CNT`, `PRE_OCCUPPY_PORTS_RATE`, `PRE_PORTS`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（3 个）**：
  - 上月剩余端口数（`PRE_FREE_PORTS_CNT`）
  - 上月端口利用率（`PRE_OCCUPPY_PORTS_RATE`）
  - 上月端口总数（`PRE_PORTS`）

### 场景：维度：通用

- **涉及字段**：`FIBER_CNT`, `PORTS`
- **分类编码**：-
- **单位**：-
- **可产出的指标（2 个）**：
  - 分纤箱数量（`FIBER_CNT`）
  - 端口数（`PORTS`）

### 场景：维度：ZX

- **涉及字段**：`ZX_CNT`, `ZX_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（2 个）**：
  - 商客户直销人数占比（`ZX_RATE`）
  - 商客直销人数（`ZX_CNT`）

### 场景：维度：MGR

- **涉及字段**：`MGR_CNT`, `MGR_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（2 个）**：
  - 商客经理人数（`MGR_CNT`）
  - 商客经理人数占比（`MGR_RATE`）

### 场景：维度：CUST

- **涉及字段**：`CUST_VERIFY_CNT`, `CUST_VERIFY_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（2 个）**：
  - 当月企业核实数（`CUST_VERIFY_CNT`）
  - 当月企业核实率（`CUST_VERIFY_RATE`）

### 场景：维度：BUILD

- **涉及字段**：`BUILD_VERIFY_CNT`, `BUILD_VERIFY_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（2 个）**：
  - 当月建筑核实数（`BUILD_VERIFY_CNT`）
  - 当月建筑核实率（`BUILD_VERIFY_RATE`）

### 场景：维度：NOCOVER

- **涉及字段**：`NOCOVER_PACKAGE_CNT`, `NOCOVER_PACKAGE_HB`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（2 个）**：
  - 未覆盖区域数（`NOCOVER_PACKAGE_CNT`）
  - 未覆盖区域数环比（`NOCOVER_PACKAGE_HB`）

### 场景：维度：ESOP

- **涉及字段**：`ESOP_CELL_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - ESOP小区数量（`ESOP_CELL_CNT`）

### 场景：维度：FREE

- **涉及字段**：`FREE_PORTS_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 剩余端口数（`FREE_PORTS_CNT`）

### 场景：维度：KD

- **涉及字段**：`KD_CUST_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 宽带客户数（`KD_CUST_CNT`）

### 场景：维度：ST

- **涉及字段**：`ST_CHANNEL_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 生态渠道人数（`ST_CHANNEL_CNT`）

### 场景：维度：SH

- **涉及字段**：`SH_CHANNEL_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 社会渠道人数（`SH_CHANNEL_CNT`）

### 场景：维度：OCCUPPY

- **涉及字段**：`OCCUPPY_PORTS_RATE`
- **分类编码**：-
- **单位**：%
- **可产出的指标（1 个）**：
  - 端口利用率（`OCCUPPY_PORTS_RATE`）

### 场景：维度：GRID

- **涉及字段**：`GRID_CNT`
- **分类编码**：7
- **单位**：-
- **可产出的指标（1 个）**：
  - 网格数（`GRID_CNT`）

### 场景：维度：ZY

- **涉及字段**：`ZY_CHANNEL_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 自有渠道人数（`ZY_CHANNEL_CNT`）

## TB_KR_GRP_SK_POI_KD_SHARES_DAY（共 36 个指标）

### 场景：INDUS_LVL1_CODE='share_indus_lvl_1_12' AND INDUS_LVL2_CODE='all'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 住宿服务-电信宽带数（`DX_KD_CNT`）
  - 住宿服务-移动份额（`YD_KD_RATE`）
  - 住宿服务-移动宽带数（`YD_KD_CNT`）
  - 住宿服务-联通宽带数（`LT_KD_CNT`）

### 场景：INDUS_LVL1_CODE='share_indus_lvl_1_7' AND INDUS_LVL2_CODE='all'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 体育休闲服务-电信宽带数（`DX_KD_CNT`）
  - 体育休闲服务-移动份额（`YD_KD_RATE`）
  - 体育休闲服务-移动宽带数（`YD_KD_CNT`）
  - 体育休闲服务-联通宽带数（`LT_KD_CNT`）

### 场景：INDUS_LVL1_CODE='share_indus_lvl_1_8' AND INDUS_LVL2_CODE='all'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 医疗保健服务-电信宽带数（`DX_KD_CNT`）
  - 医疗保健服务-移动份额（`YD_KD_RATE`）
  - 医疗保健服务-移动宽带数（`YD_KD_CNT`）
  - 医疗保健服务-联通宽带数（`LT_KD_CNT`）

### 场景：INDUS_LVL1_CODE='share_indus_lvl_1_3' AND INDUS_LVL2_CODE='all'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 汽车服务-电信宽带数（`DX_KD_CNT`）
  - 汽车服务-移动份额（`YD_KD_RATE`）
  - 汽车服务-移动宽带数（`YD_KD_CNT`）
  - 汽车服务-联通宽带数（`LT_KD_CNT`）

### 场景：INDUS_LVL1_CODE='share_indus_lvl_1_6' AND INDUS_LVL2_CODE='all'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 生活服务-电信宽带数（`DX_KD_CNT`）
  - 生活服务-移动份额（`YD_KD_RATE`）
  - 生活服务-移动宽带数（`YD_KD_CNT`）
  - 生活服务-联通宽带数（`LT_KD_CNT`）

### 场景：INDUS_LVL1_CODE='share_indus_lvl_1_11' AND INDUS_LVL2_CODE='all'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 科教文化服务-电信宽带数（`DX_KD_CNT`）
  - 科教文化服务-移动份额（`YD_KD_RATE`）
  - 科教文化服务-移动宽带数（`YD_KD_CNT`）
  - 科教文化服务-联通宽带数（`LT_KD_CNT`）

### 场景：INDUS_LVL1_CODE='share_indus_lvl_1_2' AND INDUS_LVL2_CODE='all'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 购物服务-电信宽带数（`DX_KD_CNT`）
  - 购物服务-移动份额（`YD_KD_RATE`）
  - 购物服务-移动宽带数（`YD_KD_CNT`）
  - 购物服务-联通宽带数（`LT_KD_CNT`）

### 场景：INDUS_LVL1_CODE='share_indus_lvl_1_10' AND INDUS_LVL2_CODE='all'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 金融保险服务-电信宽带数（`DX_KD_CNT`）
  - 金融保险服务-移动份额（`YD_KD_RATE`）
  - 金融保险服务-移动宽带数（`YD_KD_CNT`）
  - 金融保险服务-联通宽带数（`LT_KD_CNT`）

### 场景：INDUS_LVL1_CODE='share_indus_lvl_1_1' AND INDUS_LVL2_CODE='all'

- **涉及字段**：`DX_KD_CNT`, `LT_KD_CNT`, `YD_KD_CNT`, `YD_KD_RATE`
- **分类编码**：2
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 餐饮服务-电信宽带数（`DX_KD_CNT`）
  - 餐饮服务-移动份额（`YD_KD_RATE`）
  - 餐饮服务-移动宽带数（`YD_KD_CNT`）
  - 餐饮服务-联通宽带数（`LT_KD_CNT`）

## TB_KR_GRP_SK_FCP_TOTAL_FEE_DAY（共 30 个指标）

### 场景：维度：Y

- **涉及字段**：`Y_BP_FEE`, `Y_BP_FEE_TB`, `Y_BP_YHH_FEE`, `Y_KD_FEE`, `Y_KD_FEE_TB`, `Y_KD_YHH_FEE`, `Y_TOTAL_FEE`, `Y_TOTAL_FEE_HB`, `Y_TOTAL_FEE_TB`, `Y_TOTAL_YHH_FEE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（10 个）**：
  - 中小企业（基于标品）优后收入-年收入（`Y_BP_YHH_FEE`）
  - 中小企业（基于标品）年收入-同比增量（`Y_BP_FEE_TB`）
  - 中小企业（基于标品）收入-年收入（`Y_BP_FEE`）
  - 八类场景（基于线）优后收入-年收入（`Y_KD_YHH_FEE`）
  - 八类场景（基于线）年收入-同比增量（`Y_KD_FEE_TB`）
  - 八类场景（基于线）收入-年收入（`Y_KD_FEE`）
  - 商客优后收入-年收入（`Y_TOTAL_YHH_FEE`）
  - 商客年收入-同比增量（`Y_TOTAL_FEE_TB`）
  - 商客年收入-环比（`Y_TOTAL_FEE_HB`）
  - 商客收入-年收入（`Y_TOTAL_FEE`）

### 场景：维度：DAY

- **涉及字段**：`DAY_BP_FEE`, `DAY_BP_FEE_TB`, `DAY_BP_YHH_FEE`, `DAY_KD_FEE`, `DAY_KD_FEE_TB`, `DAY_KD_YHH_FEE`, `DAY_TOTAL_FEE`, `DAY_TOTAL_FEE_HB`, `DAY_TOTAL_FEE_TB`, `DAY_TOTAL_YHH_FEE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（10 个）**：
  - 中小企业（基于标品）优后收入-日收入（`DAY_BP_YHH_FEE`）
  - 中小企业（基于标品）收入-日收入（`DAY_BP_FEE`）
  - 中小企业（基于标品）日收入-同比增量（`DAY_BP_FEE_TB`）
  - 八类场景（基于线）优后收入-日收入（`DAY_KD_YHH_FEE`）
  - 八类场景（基于线）收入-日收入（`DAY_KD_FEE`）
  - 八类场景（基于线）日收入-同比增量（`DAY_KD_FEE_TB`）
  - 商客优后收入-日收入（`DAY_TOTAL_YHH_FEE`）
  - 商客收入-日收入（`DAY_TOTAL_FEE`）
  - 商客日收入-同比增量（`DAY_TOTAL_FEE_TB`）
  - 商客日收入-环比（`DAY_TOTAL_FEE_HB`）

### 场景：维度：MON

- **涉及字段**：`MON_BP_FEE`, `MON_BP_FEE_TB`, `MON_BP_YHH_FEE`, `MON_KD_FEE`, `MON_KD_FEE_TB`, `MON_KD_YHH_FEE`, `MON_TOTAL_FEE`, `MON_TOTAL_FEE_HB`, `MON_TOTAL_FEE_TB`, `MON_TOTAL_YHH_FEE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（10 个）**：
  - 中小企业（基于标品）优后收入-月收入（`MON_BP_YHH_FEE`）
  - 中小企业（基于标品）收入-月收入（`MON_BP_FEE`）
  - 中小企业（基于标品）月收入-同比增量（`MON_BP_FEE_TB`）
  - 八类场景（基于线）优后收入-月收入（`MON_KD_YHH_FEE`）
  - 八类场景（基于线）收入-月收入（`MON_KD_FEE`）
  - 八类场景（基于线）月收入-同比增量（`MON_KD_FEE_TB`）
  - 商客优后收入-月收入（`MON_TOTAL_YHH_FEE`）
  - 商客收入月收入（`MON_TOTAL_FEE`）
  - 商客月收入-同比增量（`MON_TOTAL_FEE_TB`）
  - 商客月收入-环比（`MON_TOTAL_FEE_HB`）

## TB_KR_GRP_SK_BIG_ZX_CUST_DAY（共 20 个指标）

### 场景：维度：MEDICAL

- **涉及字段**：`MEDICAL_CUST_CNT`, `MEDICAL_CUST_FEE`, `MEDICAL_CUST_FEE_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（3 个）**：
  - 医卫康养单位收入（`MEDICAL_CUST_FEE`）
  - 医卫康养单位数（`MEDICAL_CUST_CNT`）
  - 医卫康养收入占比（`MEDICAL_CUST_FEE_RATE`）

### 场景：维度：CLSX

- **涉及字段**：`CLSX_CUST_CNT`, `CLSX_CUST_FEE`, `CLSX_CUST_FEE_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（3 个）**：
  - 存量双线单位数（`CLSX_CUST_CNT`）
  - 存量双线收入（`CLSX_CUST_FEE`）
  - 存量双线收入占比（`CLSX_CUST_FEE_RATE`）

### 场景：维度：CLWX

- **涉及字段**：`CLWX_CUST_CNT`, `CLWX_CUST_FEE`, `CLWX_CUST_FEE_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（3 个）**：
  - 存量无线单位数（`CLWX_CUST_CNT`）
  - 存量无线收入（`CLWX_CUST_FEE`）
  - 存量无线收入占比（`CLWX_CUST_FEE_RATE`）

### 场景：维度：EDU

- **涉及字段**：`EDU_CUST_CNT`, `EDU_CUST_FEE`, `EDU_CUST_FEE_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（3 个）**：
  - 教育培训单位收入（`EDU_CUST_FEE`）
  - 教育培训单位数（`EDU_CUST_CNT`）
  - 教育培训收入占比（`EDU_CUST_FEE_RATE`）

### 场景：维度：EC

- **涉及字段**：`EC_CUST_CNT`, `EC_CUST_FEE`, `EC_CUST_FEE_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（3 个）**：
  - 电商直播单位收入（`EC_CUST_FEE`）
  - 电商直播单位数（`EC_CUST_CNT`）
  - 电商直播收入占比（`EC_CUST_FEE_RATE`）

### 场景：维度：FOOD

- **涉及字段**：`FOOD_CUST_CNT`, `FOOD_CUST_FEE`, `FOOD_CUST_FEE_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（3 个）**：
  - 食品加工单位收入（`FOOD_CUST_FEE`）
  - 食品加工单位数（`FOOD_CUST_CNT`）
  - 食品加工收入占比（`FOOD_CUST_FEE_RATE`）

### 场景：维度：BP

- **涉及字段**：`BP_FEE`, `BP_FEE_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（2 个）**：
  - 2+6标品收入（`BP_FEE`）
  - 2+6标品收入占比（`BP_FEE_RATE`）

## TB_KR_GRP_SK_GRP_TOL_DAY（共 19 个指标）

### 场景：ZX_CATEGORY_IDS='all' AND GRID_TYPE='all'

- **涉及字段**：`BD_GRP_CNT`, `BP_PER_RATE`, `COVER_GRP_CNT`, `DX_KD_CNT`, `GRP_CNT`, `GRP_DH_CNT`, `GRP_YH_CNT`, `GRP_YH_RATE`, `INPUT_GRP_CNT`, `LT_KD_CNT`, `MP_CNT`, `MP_RATE`, `MP_Y_CNT`, `MP_Y_RATE`, `NO_COVER_GRP_CNT`, `QT_KD_CNT`, `RECORD_CNT`, `RECORD_RATE`, `YD_KD_CNT`
- **分类编码**：6
- **单位**：%, -
- **可产出的指标（19 个）**：
  - 人工录入企业数（`INPUT_GRP_CNT`）
  - 企业数（`GRP_CNT`）
  - 企业核实率（`GRP_YH_RATE`）
  - 其他宽带企业数（`QT_KD_CNT`）
  - 图商提供企业数（`BD_GRP_CNT`）
  - 已核实企业数（`GRP_YH_CNT`）
  - 建档率（`RECORD_RATE`）
  - 建档集团数（`RECORD_CNT`）
  - 弱覆盖企业数（`NO_COVER_GRP_CNT`）
  - 当年企业走访率（`MP_Y_RATE`）
  - 当年走访企业数（`MP_Y_CNT`）
  - 当月企业走访率（`MP_RATE`）
  - 当月走访企业数（`MP_CNT`）
  - 待核实企业数（`GRP_DH_CNT`）
  - 标品渗透率（`BP_PER_RATE`）
  - 电信宽带企业数（`DX_KD_CNT`）
  - 移动宽带企业数（`YD_KD_CNT`）
  - 网格覆盖企业数（`COVER_GRP_CNT`）
  - 联通宽带企业数（`LT_KD_CNT`）

## TB_KR_GRP_SK_POI_TOL_DAY（共 18 个指标）

### 场景：GRID_TYPE='all'

- **涉及字段**：`BD_POI_CNT`, `COVER_POI_CNT`, `DX_KD_CNT`, `INPUT_POI_CNT`, `LT_KD_CNT`, `MP_POI_CNT`, `MP_POI_RATE`, `MP_POI_Y_CNT`, `MP_POI_Y_RATE`, `MP_YWPOI_CNT`, `MP_YWPOI_Y_CNT`, `NO_COVER_POI_CNT`, `NO_COVER_POI_RATE`, `POI_CNT`, `QT_KD_CNT`, `SK_CUST_CNT`, `YD_KD_CNT`, `YW_POI_CNT`
- **分类编码**：-, 4
- **单位**：%, -
- **可产出的指标（18 个）**：
  - 人工录入商铺数（`INPUT_POI_CNT`）
  - 其他宽带商铺数（`QT_KD_CNT`）
  - 商客客户数（`SK_CUST_CNT`）
  - 商铺数（`POI_CNT`）
  - 图商提供商铺数（`BD_POI_CNT`）
  - 异网商铺数（`YW_POI_CNT`）
  - 弱覆盖商铺占比（`NO_COVER_POI_RATE`）
  - 弱覆盖商铺数（`NO_COVER_POI_CNT`）
  - 当年商铺走访率（`MP_POI_Y_RATE`）
  - 当年走访商铺数（`MP_POI_Y_CNT`）
  - 当年走访异网商铺数（`MP_YWPOI_Y_CNT`）
  - 当月商铺走访率（`MP_POI_RATE`）
  - 当月走访商铺数（`MP_POI_CNT`）
  - 当月走访异网商铺数（`MP_YWPOI_CNT`）
  - 电信宽带商铺数（`DX_KD_CNT`）
  - 移动宽带商铺数（`YD_KD_CNT`）
  - 网络覆盖商铺数（`COVER_POI_CNT`）
  - 联通宽带商铺数（`LT_KD_CNT`）

## TB_KR_GRP_SK_LOWPACK_TOTAL_MON（共 18 个指标）

### 场景：维度：MP

- **涉及字段**：`MP_LOWSHARE_CNT`, `MP_LOWSHARE_POI_CNT`, `MP_YW_POI_CNT`, `MP_YW_POI_RATE`
- **分类编码**：10
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 低占区域打卡商铺数（`MP_LOWSHARE_POI_CNT`）
  - 低占区域打卡异网店铺占比（`MP_YW_POI_RATE`）
  - 低占区域打卡异网店铺数（`MP_YW_POI_CNT`）
  - 低占区域打卡次数（`MP_LOWSHARE_CNT`）

### 场景：维度：LOW

- **涉及字段**：`LOW_LOWSHARE_10_CNT`, `LOW_LOWSHARE_RATIO_CNT`
- **分类编码**：10
- **单位**：-
- **可产出的指标（2 个）**：
  - 份额环比下降的区域数（`LOW_LOWSHARE_RATIO_CNT`）
  - 份额较拍照下降的区域数（`LOW_LOWSHARE_10_CNT`）

### 场景：维度：UP

- **涉及字段**：`UP_LOWSHARE_RATIO_CNT`, `UP_PACKAGE_10_CNT`
- **分类编码**：10
- **单位**：-
- **可产出的指标（2 个）**：
  - 份额环比提升的区域数（`UP_LOWSHARE_RATIO_CNT`）
  - 份额较拍照提升的区域数（`UP_PACKAGE_10_CNT`）

### 场景：维度：DELIST

- **涉及字段**：`DELIST_LOWSHARE_CNT`, `DELIST_LOWSHARE_RATE`
- **分类编码**：10
- **单位**：%, -
- **可产出的指标（2 个）**：
  - 摘牌拍照区域数（`DELIST_LOWSHARE_CNT`）
  - 摘牌率（`DELIST_LOWSHARE_RATE`）

### 场景：维度：FTTR

- **涉及字段**：`FTTR_XZ_CNT`
- **分类编码**：10
- **单位**：-
- **可产出的指标（1 个）**：
  - 低占区域-FTTR/FTTO（`FTTR_XZ_CNT`）

### 场景：维度：SDJ

- **涉及字段**：`SDJ_XZ_CNT`
- **分类编码**：10
- **单位**：-
- **可产出的指标（1 个）**：
  - 低占区域-三大件（`SDJ_XZ_CNT`）

### 场景：维度：YDN

- **涉及字段**：`YDN_XZ_CNT`
- **分类编码**：10
- **单位**：-
- **可产出的指标（1 个）**：
  - 低占区域-云电脑（`YDN_XZ_CNT`）

### 场景：维度：JZTC

- **涉及字段**：`JZTC_XZ_CNT`
- **分类编码**：10
- **单位**：-
- **可产出的指标（1 个）**：
  - 低占区域-商客价值套餐（`JZTC_XZ_CNT`）

### 场景：维度：SKKD

- **涉及字段**：`SKKD_XZ_CNT`
- **分类编码**：10
- **单位**：-
- **可产出的指标（1 个）**：
  - 低占区域-商客宽带（`SKKD_XZ_CNT`）

### 场景：维度：ANFANG

- **涉及字段**：`ANFANG_XZ_CNT`
- **分类编码**：10
- **单位**：-
- **可产出的指标（1 个）**：
  - 低占区域-安防（`ANFANG_XZ_CNT`）

### 场景：维度：YW

- **涉及字段**：`YW_CARD_CNT`
- **分类编码**：10
- **单位**：-
- **可产出的指标（1 个）**：
  - 低占区域-拉新异网号卡（`YW_CARD_CNT`）

### 场景：维度：LOWSHARE

- **涉及字段**：`LOWSHARE_CNT`
- **分类编码**：10
- **单位**：-
- **可产出的指标（1 个）**：
  - 攻坚区域数（`LOWSHARE_CNT`）

## TB_KR_GRP_SK_CUST_EFFICACY_DAY（共 18 个指标）

### 场景：维度：SKZX

- **涉及字段**：`SKZX_AVG_EFFICACY`, `SKZX_AVG_PROD_CNT`, `SKZX_EQUAL_PROD_RATE`, `SKZX_PROD_CNT`, `SKZX_SALE_CNT`
- **分类编码**：6
- **单位**：%, -
- **可产出的指标（5 个）**：
  - 商客直销-当月2+6标品办理量（`SKZX_PROD_CNT`）
  - 商客直销-当月人均办理量（`SKZX_AVG_PROD_CNT`）
  - 商客直销-当月人均效能（`SKZX_AVG_EFFICACY`）
  - 商客直销-有销数量（`SKZX_SALE_CNT`）
  - 商客直销-百元等效整体占比（`SKZX_EQUAL_PROD_RATE`）

### 场景：维度：SKMGR

- **涉及字段**：`SKMGR_AVG_EFFICACY`, `SKMGR_AVG_PROD_CNT`, `SKMGR_EQUAL_PROD_RATE`, `SKMGR_PROD_CNT`, `SKMGR_SALE_CNT`
- **分类编码**：6
- **单位**：%, -
- **可产出的指标（5 个）**：
  - 商客经理-当月2+6标品办理量（`SKMGR_PROD_CNT`）
  - 商客经理-当月人均办理量（`SKMGR_AVG_PROD_CNT`）
  - 商客经理-当月人均效能（`SKMGR_AVG_EFFICACY`）
  - 商客经理-有销数量（`SKMGR_SALE_CNT`）
  - 商客经理-百元等效整体占比（`SKMGR_EQUAL_PROD_RATE`）

### 场景：维度：QTCH

- **涉及字段**：`QTCH_AVG_PROD_CNT`, `QTCH_EQUAL_PROD_RATE`, `QTCH_PROD_CNT`, `QTCH_SALE_CNT`
- **分类编码**：6
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 其他渠道-当月2+6标品办理量（`QTCH_PROD_CNT`）
  - 其他渠道-当月人均办理量（`QTCH_AVG_PROD_CNT`）
  - 其他渠道-有销数量（`QTCH_SALE_CNT`）
  - 其他渠道-百元等效整体占比（`QTCH_EQUAL_PROD_RATE`）

### 场景：维度：SHCH

- **涉及字段**：`SHCH_AVG_PROD_CNT`, `SHCH_EQUAL_PROD_RATE`, `SHCH_PROD_CNT`, `SHCH_SALE_CNT`
- **分类编码**：6
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 社会渠道-当月2+6标品办理量（`SHCH_PROD_CNT`）
  - 社会渠道-当月人均办理量（`SHCH_AVG_PROD_CNT`）
  - 社会渠道-有销数量（`SHCH_SALE_CNT`）
  - 社会渠道-百元等效整体占比（`SHCH_EQUAL_PROD_RATE`）

## TB_KR_GRP_SK_YW_POI_RH_DAY（共 13 个指标）

### 场景：维度：PZ

- **涉及字段**：`PZ_CLOSE_CNT`, `PZ_REMAIN_CNT`, `PZ_WINBACK_CNT`, `PZ_WINBACK_RATE`, `PZ_YW_CNT`
- **分类编码**：11
- **单位**：%, -
- **可产出的指标（5 个）**：
  - 剩余未赢回量（`PZ_REMAIN_CNT`）
  - 已下线量（`PZ_CLOSE_CNT`）
  - 当月地图下单赢回量（`PZ_WINBACK_CNT`）
  - 拍照异网商铺数（`PZ_YW_CNT`）
  - 赢回率（`PZ_WINBACK_RATE`）

### 场景：维度：JZTC

- **涉及字段**：`JZTC_NEW_YH_CNT`, `JZTC_YH_CNT`
- **分类编码**：11
- **单位**：-
- **可产出的指标（2 个）**：
  - 异网攻坚拉新-其中新入网商客价值套餐（`JZTC_NEW_YH_CNT`）
  - 异网攻坚拉新-商客价值套餐（`JZTC_YH_CNT`）

### 场景：维度：FTTR

- **涉及字段**：`FTTR_YH_CNT`
- **分类编码**：11
- **单位**：-
- **可产出的指标（1 个）**：
  - 异网攻坚拉新-FTTR/FTTO（`FTTR_YH_CNT`）

### 场景：维度：SDJ

- **涉及字段**：`SDJ_YH_CNT`
- **分类编码**：11
- **单位**：-
- **可产出的指标（1 个）**：
  - 异网攻坚拉新-三大件（`SDJ_YH_CNT`）

### 场景：维度：YDN

- **涉及字段**：`YDN_YH_CNT`
- **分类编码**：11
- **单位**：-
- **可产出的指标（1 个）**：
  - 异网攻坚拉新-云电脑（`YDN_YH_CNT`）

### 场景：维度：SKKD

- **涉及字段**：`SKKD_YH_CNT`
- **分类编码**：11
- **单位**：-
- **可产出的指标（1 个）**：
  - 异网攻坚拉新-商客宽带（`SKKD_YH_CNT`）

### 场景：维度：ANFANG

- **涉及字段**：`ANFANG_YH_CNT`
- **分类编码**：11
- **单位**：-
- **可产出的指标（1 个）**：
  - 异网攻坚拉新-安防（`ANFANG_YH_CNT`）

### 场景：维度：YW

- **涉及字段**：`YW_CARD_YH_CNT`
- **分类编码**：11
- **单位**：-
- **可产出的指标（1 个）**：
  - 异网攻坚拉新-拉新异网号卡（`YW_CARD_YH_CNT`）

## TB_KR_GRP_SK_NBUILD_TOL_DAY（共 13 个指标）

### 场景：GRID_TYPE='all'

- **涉及字段**：`BD_NBUILD_CNT`, `COVER_NBUILD_CNT`, `INPUT_NBUILD_CNT`, `MP_BUILD_CNT`, `MP_BUILD_RATE`, `MP_BUILD_Y_CNT`, `MP_BUILD_Y_RATE`, `NBUILD_CNT`, `NBUILD_DH_CNT`, `NBUILD_YH_CNT`, `NO_COVER_NBUILD_CNT`, `NO_PACK_NBUILD_CNT`, `PACKED_NBUILD_CNT`
- **分类编码**：5
- **单位**：%, -
- **可产出的指标（13 个）**：
  - 人工录入建筑物数（`INPUT_NBUILD_CNT`）
  - 图商提供建筑物数（`BD_NBUILD_CNT`）
  - 已分包建筑物数（`PACKED_NBUILD_CNT`）
  - 已核实建筑物数（`NBUILD_YH_CNT`）
  - 建筑物数（`NBUILD_CNT`）
  - 弱覆盖建筑物数（`NO_COVER_NBUILD_CNT`）
  - 当年建筑物走访率（`MP_BUILD_Y_RATE`）
  - 当年走访建筑物数（`MP_BUILD_Y_CNT`）
  - 当月建筑物走访率（`MP_BUILD_RATE`）
  - 当月走访建筑物数（`MP_BUILD_CNT`）
  - 待核实建筑物数（`NBUILD_DH_CNT`）
  - 未分包建筑物数（`NO_PACK_NBUILD_CNT`）
  - 网络覆盖建筑物数（`COVER_NBUILD_CNT`）

## TB_KR_GRP_SK_LINKBRAND_RH_DAY（共 10 个指标）

### 场景：LINK_TYPE = 1

- **涉及字段**：`BRAND_CNT`, `CUST_CNT`, `LINK_TYPE`, `POI_CNT`, `POI_DX_CNT`, `POI_LT_CNT`, `POI_YD_CNT`, `POI_YD_RATE`, `REGIST_BRAND_CNT`, `REGIST_BRAND_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（10 个）**：
  - 品牌总部所在地市企业数（`CUST_CNT`）
  - 品牌数（`BRAND_CNT`）
  - 连锁品牌已建档数（`REGIST_BRAND_CNT`）
  - 连锁品牌建档率（`REGIST_BRAND_RATE`）
  - 连锁品牌门店规模（`POI_CNT`）
  - 连锁电信宽带数（`POI_DX_CNT`）
  - 连锁移动份额（`POI_YD_RATE`）
  - 连锁移动宽带数（`POI_YD_CNT`）
  - 连锁类型（`LINK_TYPE`）
  - 连锁联通宽带数（`POI_LT_CNT`）

## TB_KR_GRP_SK_STAFF_ACTIVE_DAY（共 9 个指标）

### 场景：维度：D

- **涉及字段**：`D_ALL_LOGIN_CNT`, `D_ALL_LOGIN_RATE`, `D_FLW_LOGIN_CNT`, `D_FLW_LOGIN_RATE`, `D_MGR_LOGIN_CNT`, `D_MGR_LOGIN_RATE`
- **分类编码**：12
- **单位**：%, -
- **可产出的指标（6 个）**：
  - 一线人员-活跃率（`D_FLW_LOGIN_RATE`）
  - 一线人员-登录人数（`D_FLW_LOGIN_CNT`）
  - 活跃率（`D_ALL_LOGIN_RATE`）
  - 登录人数（`D_ALL_LOGIN_CNT`）
  - 管理人员-活跃率（`D_MGR_LOGIN_RATE`）
  - 管理人员-登录人数（`D_MGR_LOGIN_CNT`）

### 场景：维度：FLW

- **涉及字段**：`FLW_CNT`
- **分类编码**：12
- **单位**：-
- **可产出的指标（1 个）**：
  - 一线人员-赋权人数（`FLW_CNT`）

### 场景：维度：MGR

- **涉及字段**：`MGR_CNT`
- **分类编码**：12
- **单位**：-
- **可产出的指标（1 个）**：
  - 管理人员-赋权人数（`MGR_CNT`）

### 场景：维度：ALL

- **涉及字段**：`ALL_CNT`
- **分类编码**：12
- **单位**：-
- **可产出的指标（1 个）**：
  - 赋权人数（`ALL_CNT`）

## TB_KR_GRP_SK_ZY_PORTS_DAY（共 9 个指标）

### 场景：(无条件)

- **涉及字段**：`SK_ESOP_CELL_CNT`, `SK_FIBER_CNT`, `SK_FREE_PORTS_CNT`, `SK_FREE_PORTS_LM_CNT`, `SK_LM_PORTS`, `SK_OCCUPPY_EQUIP_PORTS`, `SK_OCCUPPY_PORTS_LM_RATE`, `SK_OCCUPPY_PORTS_RATE`, `SK_PORTS`
- **分类编码**：9
- **单位**：%, -
- **可产出的指标（9 个）**：
  - 商客ESOP小区数量（`SK_ESOP_CELL_CNT`）
  - 商客上月剩余端口数（`SK_FREE_PORTS_LM_CNT`）
  - 商客上月端口利用率（`SK_OCCUPPY_PORTS_LM_RATE`）
  - 商客上月端口总数（`SK_LM_PORTS`）
  - 商客分纤箱数量（`SK_FIBER_CNT`）
  - 商客剩余端口数（`SK_FREE_PORTS_CNT`）
  - 商客已用端口数（`SK_OCCUPPY_EQUIP_PORTS`）
  - 商客总端口数（`SK_PORTS`）
  - 商客端口利用率（`SK_OCCUPPY_PORTS_RATE`）

## TB_KR_GRP_SK_SKSC_FEE_DAY（共 8 个指标）

### 场景：维度：Y

- **涉及字段**：`Y_ALL_YHH_FEE`, `Y_SL_YHH_FEE`, `Y_TX_YHH_FEE`, `Y_ZN_YHH_FEE`
- **分类编码**：1
- **单位**：万元
- **可产出的指标（4 个）**：
  - 当年优惠后收入（`Y_ALL_YHH_FEE`）
  - 当年优惠后智脑服务收入（`Y_ZN_YHH_FEE`）
  - 当年优惠后算力服务收入（`Y_SL_YHH_FEE`）
  - 当年优惠后通信服务收入（`Y_TX_YHH_FEE`）

### 场景：维度：M

- **涉及字段**：`M_ALL_YHH_FEE`, `M_SL_YHH_FEE`, `M_TX_YHH_FEE`, `M_ZN_YHH_FEE`
- **分类编码**：1
- **单位**：万元
- **可产出的指标（4 个）**：
  - 当月优惠后收入（`M_ALL_YHH_FEE`）
  - 当月优惠后智脑服务收入（`M_ZN_YHH_FEE`）
  - 当月优惠后算力服务收入（`M_SL_YHH_FEE`）
  - 当月优惠后通信服务收入（`M_TX_YHH_FEE`）

## TB_KR_GRP_SK_ALL_PROD_DEV_DAY（共 7 个指标）

### 场景：维度：MXZ

- **涉及字段**：`MXZ_GRP_PROD_CNT`, `MXZ_GRP_PROD_HB`, `MXZ_SDJ_CNT`, `MXZ_SDJ_HB`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（4 个）**：
  - 三大件月新增（`MXZ_SDJ_CNT`）
  - 三大件月新增环比（`MXZ_SDJ_HB`）
  - 中小集团2+6月新增（`MXZ_GRP_PROD_CNT`）
  - 中小集团2+6月新增环比（`MXZ_GRP_PROD_HB`）

### 场景：维度：DXZ

- **涉及字段**：`DXZ_GRP_PROD_CNT`, `DXZ_SDJ_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（2 个）**：
  - 三大件日新增（`DXZ_SDJ_CNT`）
  - 中小集团2+6日新增（`DXZ_GRP_PROD_CNT`）

### 场景：维度：NEW

- **涉及字段**：`NEW_OFFER_CNT`
- **分类编码**：-
- **单位**：-
- **可产出的指标（1 个）**：
  - 拉新套餐（`NEW_OFFER_CNT`）

## TB_KR_GRP_SK_EVALUATE_DAY（共 7 个指标）

### 场景：维度：QM

- **涉及字段**：`QM_SAAS_RATE`, `QM_SDJ_RATE`
- **分类编码**：3
- **单位**：%
- **可产出的指标（2 个）**：
  - 三大件渗透率（`QM_SDJ_RATE`）
  - 轻SaaS产品渗透率（`QM_SAAS_RATE`）

### 场景：维度：SDJ

- **涉及字段**：`SDJ_CONTRI_RATE`
- **分类编码**：3
- **单位**：%
- **可产出的指标（1 个）**：
  - 三大件净增贡献占比（`SDJ_CONTRI_RATE`）

### 场景：维度：MAH

- **涉及字段**：`MAH_CUST_RATE`
- **分类编码**：3
- **单位**：%
- **可产出的指标（1 个）**：
  - 中高端客户净增贡献占比（`MAH_CUST_RATE`）

### 场景：维度：KD

- **涉及字段**：`KD_CONTRI_RATE`
- **分类编码**：3
- **单位**：%
- **可产出的指标（1 个）**：
  - 宽带净增贡献占比（`KD_CONTRI_RATE`）

### 场景：维度：LX

- **涉及字段**：`LX_YW_RATE`
- **分类编码**：3
- **单位**：%
- **可产出的指标（1 个）**：
  - 拉新异网率（`LX_YW_RATE`）

### 场景：维度：PERFORM

- **涉及字段**：`PERFORM_SCORE`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 评估得分（`PERFORM_SCORE`）

## TB_KR_GRP_SK_FZZL_LW_TOTAL_DAY（共 6 个指标）

### 场景：(无条件)

- **涉及字段**：`SK_KD_CJLW_LWL`, `SK_KD_CJLW_USERS`, `SK_KD_XHLW_LWL`, `SK_KD_XHLW_USERS`, `SK_LW_M_LWL`, `SK_LW_M_USERS`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（6 个）**：
  - 宽带流失率（`SK_LW_M_LWL`）
  - 宽带流失量（`SK_LW_M_USERS`）
  - 拆机流失率（`SK_KD_CJLW_LWL`）
  - 拆机流失量（`SK_KD_CJLW_USERS`）
  - 销号流失率（`SK_KD_XHLW_LWL`）
  - 销号流失量（`SK_KD_XHLW_USERS`）

## TB_KR_GRP_SK_LINKPOI_RH_DAY（共 6 个指标）

### 场景：LINK_TYPE = 1

- **涉及字段**：`LINK_TYPE`, `POI_CNT`, `POI_DX_CNT`, `POI_LT_CNT`, `POI_YD_CNT`, `POI_YD_RATE`
- **分类编码**：-
- **单位**：%, -
- **可产出的指标（6 个）**：
  - 连锁品牌门店规模（`POI_CNT`）
  - 连锁电信宽带数（`POI_DX_CNT`）
  - 连锁移动份额（`POI_YD_RATE`）
  - 连锁移动宽带数（`POI_YD_CNT`）
  - 连锁类型（`LINK_TYPE`）
  - 连锁联通宽带数（`POI_LT_CNT`）

## TB_KR_GRP_SK_CAPACITY_DAY（共 1 个指标）

### 场景：(无条件)

- **涉及字段**：`M_9_XZ_CNT`
- **分类编码**：3
- **单位**：-
- **可产出的指标（1 个）**：
  - 中小标品百元等效（`M_9_XZ_CNT`）
