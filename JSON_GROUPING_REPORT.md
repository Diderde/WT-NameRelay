# WT-NameRelay 名称数据库实际分组审计报告

> 审计方式：只读解析当前项目源 JSON，并与 Qt 资源系统内嵌内容逐字节比对。  
> 审计日期：2026-08-18  
> 本报告不对数据库作任何补号、排序、格式化或修正。

## 1. 程序实际加载的 JSON 路径

### 1.1 当前源数据库

| 模块 | 项目内实际文件 | 运行时 Qt 资源路径 |
| --- | --- | --- |
| 车组 | `app/resources/data/crew_name_groups.json` | `:/data/crew_name_groups.json` |
| 无线电 | `app/resources/data/radio_name_groups.json` | `:/data/radio_name_groups.json` |
| Bank | `app/resources/data/bank_name_groups.json` | `:/data/bank_name_groups.json` |

只找到以上三份名称数据库。`reports/radio_name_analysis.json` 和 `reports/bank_name_analysis.json` 是生成阶段的审计报告，不是运行时数据库；未发现旧版、备份、发布目录散落副本或其他同名 JSON。

### 1.2 页面与仓库加载链

- 车组页面使用 `CREW_MODULE.data_path = ":/data/crew_name_groups.json"`，由 `CrewPage` 传给 `CrewNameRepository`。
- 无线电页面使用 `RADIO_MODULE.data_path = ":/data/radio_name_groups.json"`，由同一套 `CrewPage`/`CrewNameRepository` 公共实现加载。
- Bank 页面实例化 `BankNameRepository`，其常量 `RESOURCE_PATH` 为 `:/data/bank_name_groups.json`。
- 语音处理页面实例化 `ProjectGroupRepository`，同时读取车组和无线电两个 Qt 资源；它不读取 Bank JSON。
- `app/resources/resources.qrc` 将三份源 JSON 注册到 `:/data/`，`resources_rc.py` 是程序实际导入的编译资源模块。
- 源码运行和 PyInstaller 运行都使用相同的 `:/data/...` 标识。JSON 已编译进 `resources_rc.py`/Python 归档，不依赖当前工作目录、`sys._MEIPASS` 下的独立 JSON、源 Excel、无线电参考工程或 War Thunder `sound` 目录。
- 数据生成脚本的默认输出分别指向上述三份源 JSON，但这些脚本不参与应用运行时读取。

### 1.3 源文件与内嵌资源一致性

| 模块 | 字节数 | SHA-256 | 与 QRC 内嵌内容一致 |
| --- | ---: | --- | --- |
| 车组 | 47,469 | `0ae64558009fdce691546d3c84f3f02321a567bb816ad1bb41bbc0b2d84510b9` | 是 |
| 无线电 | 67,242 | `3e1d838bbfe5b441518656f8612c81c7851c8680fdebecce9e1407e5b43923be` | 是 |
| Bank | 10,831 | `03be951475757755168da7ff057b16d6dc2eac5dfa24bb9c194cc80856082370` | 是 |

因此当前不存在“源码 JSON 已更新但程序仍加载旧内嵌资源”的情况。今后若手工修改源 JSON 却未重新运行 Qt 资源编译，才可能发生资源滞后。

## 2. 总体统计

| 模块 | 正式分类数 | 项目组数 | 完整名称数 | 未分类组 | 异常组 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 车组 | 7 | 151 | 511 | 3 | 3 |
| 无线电 | 3 | 56 | 480 | 11 | 11 |
| Bank | 2 | 52 | 104 | 0 | 0 |

这里的“异常组”仅统计缺失运行所需分类元数据的组；编号缺口、特殊拆组等提示另见第 7 节，不代表 JSON 无法加载。Bank 的项目组数按“类别/国家”计算，完整名称数按实际 `assets` 与 `main` 文件名计算。

### 2.1 车组分类统计

| 分类 | 项目组数 | 成员总数 | single | double | mixed | 其他 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| artillery | 4 | 12 | 4 | 0 | 0 | 0 |
| aviation | 1 | 3 | 1 | 0 | 0 | 0 |
| chief_m | 5 | 31 | 2 | 3 | 0 | 0 |
| commander | 43 | 149 | 32 | 9 | 2 | 0 |
| driver | 41 | 143 | 35 | 6 | 0 | 0 |
| gunner | 29 | 90 | 28 | 1 | 0 | 0 |
| loader | 25 | 75 | 25 | 0 | 0 | 0 |
| 未分类 | 3 | 8 | 3 | 0 | 0 | 0 |
| **合计** | **151** | **511** | **130** | **19** | **2** | **0** |

### 2.2 无线电分类统计

| 分类 | 项目组数 | 成员总数 | single | double | mixed | 其他 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 态势播报 | 10 | 66 | 0 | 0 | 0 | 10 |
| additional_01 | 9 | 27 | 0 | 0 | 0 | 9 |
| 信息 | 26 | 312 | 0 | 0 | 0 | 26 |
| 未分类 | 11 | 75 | 0 | 0 | 0 | 11 |
| **合计** | **56** | **480** | **0** | **0** | **0** | **56** |

无线电的“其他”由 `v_suffix`、`v_matrix_suffix` 和 `matrix_suffix` 构成，详细类型数量分别为 17、13、26。

### 2.3 Bank 分类统计

| 类别 | 国家数 | 完整配对 | 残缺配对 | 实际文件名数 |
| --- | ---: | ---: | ---: | ---: |
| common | 17 | 17 | 0 | 34 |
| ground | 35 | 35 | 0 | 70 |
| **合计** | **52** | **52** | **0** | **104** |

## 3. 车组完整分组

### 3.1 artillery

1. `voice_message_artillery_acknowledged`

   - 组键：`voice_message_artillery_acknowledged`
   - 基础名称：`voice_message_artillery_acknowledged`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`artillery`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_artillery_acknowledged_v1`
     - `voice_message_artillery_acknowledged_v2`
     - `voice_message_artillery_acknowledged_v3`

2. `voice_message_artillery_bracketed`

   - 组键：`voice_message_artillery_bracketed`
   - 基础名称：`voice_message_artillery_bracketed`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`artillery`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_artillery_bracketed_v1`
     - `voice_message_artillery_bracketed_v2`
     - `voice_message_artillery_bracketed_v3`

3. `voice_message_artillery_open_fire`

   - 组键：`voice_message_artillery_open_fire`
   - 基础名称：`voice_message_artillery_open_fire`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`artillery`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_artillery_open_fire_v1`
     - `voice_message_artillery_open_fire_v2`
     - `voice_message_artillery_open_fire_v3`

4. `voice_message_artillery_understood`

   - 组键：`voice_message_artillery_understood`
   - 基础名称：`voice_message_artillery_understood`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`artillery`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_artillery_understood_v1`
     - `voice_message_artillery_understood_v2`
     - `voice_message_artillery_understood_v3`

### 3.2 aviation

1. `voice_message_aviation_on_the_way`

   - 组键：`voice_message_aviation_on_the_way`
   - 基础名称：`voice_message_aviation_on_the_way`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`aviation`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_aviation_on_the_way_v1`
     - `voice_message_aviation_on_the_way_v2`
     - `voice_message_aviation_on_the_way_v3`

### 3.3 chief_m

1. `voice_message_chief_air_danger`

   - 组键：`voice_message_chief_air_danger`
   - 基础名称：`voice_message_chief_air_danger`
   - 命名类型：`double`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`chief_m`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_chief_air_danger_v1_1`
     - `voice_message_chief_air_danger_v1_2`
     - `voice_message_chief_air_danger_v1_3`
     - `voice_message_chief_air_danger_v2_1`
     - `voice_message_chief_air_danger_v2_2`
     - `voice_message_chief_air_danger_v2_3`

2. `voice_message_chief_artillery_danger`

   - 组键：`voice_message_chief_artillery_danger`
   - 基础名称：`voice_message_chief_artillery_danger`
   - 命名类型：`double`
   - 成员数量：8
   - `module`：`crew`
   - `category`：`chief_m`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_chief_artillery_danger_v1_1`
     - `voice_message_chief_artillery_danger_v1_2`
     - `voice_message_chief_artillery_danger_v2_1`
     - `voice_message_chief_artillery_danger_v2_2`
     - `voice_message_chief_artillery_danger_v3_1`
     - `voice_message_chief_artillery_danger_v3_2`
     - `voice_message_chief_artillery_danger_v4_1`
     - `voice_message_chief_artillery_danger_v4_2`

3. `voice_message_chief_battle_loose`

   - 组键：`voice_message_chief_battle_loose`
   - 基础名称：`voice_message_chief_battle_loose`
   - 命名类型：`single`
   - 成员数量：4
   - `module`：`crew`
   - `category`：`chief_m`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_chief_battle_loose_v1`
     - `voice_message_chief_battle_loose_v2`
     - `voice_message_chief_battle_loose_v3`
     - `voice_message_chief_battle_loose_v4`

4. `voice_message_chief_battle_start`

   - 组键：`voice_message_chief_battle_start`
   - 基础名称：`voice_message_chief_battle_start`
   - 命名类型：`double`
   - 成员数量：9
   - `module`：`crew`
   - `category`：`chief_m`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_chief_battle_start_v1_1`
     - `voice_message_chief_battle_start_v1_2`
     - `voice_message_chief_battle_start_v1_3`
     - `voice_message_chief_battle_start_v2_1`
     - `voice_message_chief_battle_start_v2_2`
     - `voice_message_chief_battle_start_v2_3`
     - `voice_message_chief_battle_start_v3_1`
     - `voice_message_chief_battle_start_v3_2`
     - `voice_message_chief_battle_start_v3_3`

5. `voice_message_chief_battle_win`

   - 组键：`voice_message_chief_battle_win`
   - 基础名称：`voice_message_chief_battle_win`
   - 命名类型：`single`
   - 成员数量：4
   - `module`：`crew`
   - `category`：`chief_m`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_chief_battle_win_v1`
     - `voice_message_chief_battle_win_v2`
     - `voice_message_chief_battle_win_v3`
     - `voice_message_chief_battle_win_v4`

### 3.4 commander

1. `voice_message_commander_art_barrage`

   - 组键：`voice_message_commander_art_barrage`
   - 基础名称：`voice_message_commander_art_barrage`
   - 命名类型：`double`
   - 成员数量：4
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_art_barrage_v1_1`
     - `voice_message_commander_art_barrage_v1_2`
     - `voice_message_commander_art_barrage_v2_1`
     - `voice_message_commander_art_barrage_v2_2`

2. `voice_message_commander_art_coordinates`

   - 组键：`voice_message_commander_art_coordinates`
   - 基础名称：`voice_message_commander_art_coordinates`
   - 命名类型：`double`
   - 成员数量：4
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_art_coordinates_v1_1`
     - `voice_message_commander_art_coordinates_v1_2`
     - `voice_message_commander_art_coordinates_v2_1`
     - `voice_message_commander_art_coordinates_v2_2`

3. `voice_message_commander_art_destroy`

   - 组键：`voice_message_commander_art_destroy`
   - 基础名称：`voice_message_commander_art_destroy`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_art_destroy_v1`
     - `voice_message_commander_art_destroy_v2`
     - `voice_message_commander_art_destroy_v3`

4. `voice_message_commander_art_on_me`

   - 组键：`voice_message_commander_art_on_me`
   - 基础名称：`voice_message_commander_art_on_me`
   - 命名类型：`double`
   - 成员数量：4
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_art_on_me_v1_1`
     - `voice_message_commander_art_on_me_v1_2`
     - `voice_message_commander_art_on_me_v2_1`
     - `voice_message_commander_art_on_me_v2_2`

5. `voice_message_commander_art_request`

   - 组键：`voice_message_commander_art_request`
   - 基础名称：`voice_message_commander_art_request`
   - 命名类型：`double`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_art_request_v1_1`
     - `voice_message_commander_art_request_v1_2`
     - `voice_message_commander_art_request_v1_3`
     - `voice_message_commander_art_request_v2_1`
     - `voice_message_commander_art_request_v2_2`
     - `voice_message_commander_art_request_v2_3`

6. `voice_message_commander_bail`

   - 组键：`voice_message_commander_bail`
   - 基础名称：`voice_message_commander_bail`
   - 命名类型：`double`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_bail_v1_1`
     - `voice_message_commander_bail_v1_2`
     - `voice_message_commander_bail_v1_3`
     - `voice_message_commander_bail_v2_1`
     - `voice_message_commander_bail_v2_2`
     - `voice_message_commander_bail_v2_3`

7. `voice_message_commander_battle_start`

   - 组键：`voice_message_commander_battle_start`
   - 基础名称：`voice_message_commander_battle_start`
   - 命名类型：`double`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_battle_start_v1_1`
     - `voice_message_commander_battle_start_v1_2`
     - `voice_message_commander_battle_start_v1_3`
     - `voice_message_commander_battle_start_v2_1`
     - `voice_message_commander_battle_start_v2_2`
     - `voice_message_commander_battle_start_v2_3`

8. `voice_message_commander_correction_left`

   - 组键：`voice_message_commander_correction_left`
   - 基础名称：`voice_message_commander_correction_left`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_correction_left_v1`
     - `voice_message_commander_correction_left_v2`
     - `voice_message_commander_correction_left_v3`

9. `voice_message_commander_correction_right`

   - 组键：`voice_message_commander_correction_right`
   - 基础名称：`voice_message_commander_correction_right`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_correction_right_v1`
     - `voice_message_commander_correction_right_v2`
     - `voice_message_commander_correction_right_v3`

10. `voice_message_commander_correction_target_destroyed_nice_shot`

   - 组键：`voice_message_commander_correction_target_destroyed_nice_shot`
   - 基础名称：`voice_message_commander_correction_target_destroyed_nice_shot`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_correction_target_destroyed_nice_shot_v1`
     - `voice_message_commander_correction_target_destroyed_nice_shot_v2`
     - `voice_message_commander_correction_target_destroyed_nice_shot_v3`

11. `voice_message_commander_crew_lost`

   - 组键：`voice_message_commander_crew_lost`
   - 基础名称：`voice_message_commander_crew_lost`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_crew_lost_v1`
     - `voice_message_commander_crew_lost_v2`
     - `voice_message_commander_crew_lost_v3`

12. `voice_message_commander_engine_start`

   - 组键：`voice_message_commander_engine_start`
   - 基础名称：`voice_message_commander_engine_start`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_engine_start_v1`
     - `voice_message_commander_engine_start_v2`
     - `voice_message_commander_engine_start_v3`

13. `voice_message_commander_engine_stop`

   - 组键：`voice_message_commander_engine_stop`
   - 基础名称：`voice_message_commander_engine_stop`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_engine_stop_v1`
     - `voice_message_commander_engine_stop_v2`
     - `voice_message_commander_engine_stop_v3`

14. `voice_message_commander_load_AP`

   - 组键：`voice_message_commander_load_AP`
   - 基础名称：`voice_message_commander_load_AP`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_AP_v1`
     - `voice_message_commander_load_AP_v2`
     - `voice_message_commander_load_AP_v3`

15. `voice_message_commander_load_APCR`

   - 组键：`voice_message_commander_load_APCR`
   - 基础名称：`voice_message_commander_load_APCR`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_APCR_v1`
     - `voice_message_commander_load_APCR_v2`
     - `voice_message_commander_load_APCR_v3`

16. `voice_message_commander_load_HE`

   - 组键：`voice_message_commander_load_HE`
   - 基础名称：`voice_message_commander_load_HE`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_HE_v1`
     - `voice_message_commander_load_HE_v2`
     - `voice_message_commander_load_HE_v3`

17. `voice_message_commander_load_HEAT`

   - 组键：`voice_message_commander_load_HEAT`
   - 基础名称：`voice_message_commander_load_HEAT`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_HEAT_v1`
     - `voice_message_commander_load_HEAT_v2`
     - `voice_message_commander_load_HEAT_v3`

18. `voice_message_commander_load_HESH`

   - 组键：`voice_message_commander_load_HESH`
   - 基础名称：`voice_message_commander_load_HESH`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_HESH_v1`
     - `voice_message_commander_load_HESH_v2`
     - `voice_message_commander_load_HESH_v3`

19. `voice_message_commander_load_canister`

   - 组键：`voice_message_commander_load_canister`
   - 基础名称：`voice_message_commander_load_canister`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_canister_v1`
     - `voice_message_commander_load_canister_v2`
     - `voice_message_commander_load_canister_v3`

20. `voice_message_commander_load_flares`

   - 组键：`voice_message_commander_load_flares`
   - 基础名称：`voice_message_commander_load_flares`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_flares_v1`
     - `voice_message_commander_load_flares_v2`
     - `voice_message_commander_load_flares_v3`

21. `voice_message_commander_load_frag`

   - 组键：`voice_message_commander_load_frag`
   - 基础名称：`voice_message_commander_load_frag`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_frag_v1`
     - `voice_message_commander_load_frag_v2`
     - `voice_message_commander_load_frag_v3`

22. `voice_message_commander_load_missile`

   - 组键：`voice_message_commander_load_missile`
   - 基础名称：`voice_message_commander_load_missile`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_missile_v1`
     - `voice_message_commander_load_missile_v2`
     - `voice_message_commander_load_missile_v3`

23. `voice_message_commander_load_sabot`

   - 组键：`voice_message_commander_load_sabot`
   - 基础名称：`voice_message_commander_load_sabot`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_sabot_v1`
     - `voice_message_commander_load_sabot_v2`
     - `voice_message_commander_load_sabot_v3`

24. `voice_message_commander_load_shrapnel`

   - 组键：`voice_message_commander_load_shrapnel`
   - 基础名称：`voice_message_commander_load_shrapnel`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_shrapnel_v1`
     - `voice_message_commander_load_shrapnel_v2`
     - `voice_message_commander_load_shrapnel_v3`

25. `voice_message_commander_load_smoke`

   - 组键：`voice_message_commander_load_smoke`
   - 基础名称：`voice_message_commander_load_smoke`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_load_smoke_v1`
     - `voice_message_commander_load_smoke_v2`
     - `voice_message_commander_load_smoke_v3`

26. `voice_message_commander_move_backward`

   - 组键：`voice_message_commander_move_backward`
   - 基础名称：`voice_message_commander_move_backward`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_move_backward_v1`
     - `voice_message_commander_move_backward_v2`
     - `voice_message_commander_move_backward_v3`

27. `voice_message_commander_move_faster`

   - 组键：`voice_message_commander_move_faster`
   - 基础名称：`voice_message_commander_move_faster`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_move_faster_v1`
     - `voice_message_commander_move_faster_v2`
     - `voice_message_commander_move_faster_v3`

28. `voice_message_commander_move_forward`

   - 组键：`voice_message_commander_move_forward`
   - 基础名称：`voice_message_commander_move_forward`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_move_forward_v1`
     - `voice_message_commander_move_forward_v2`
     - `voice_message_commander_move_forward_v3`

29. `voice_message_commander_move_revvs`

   - 组键：`voice_message_commander_move_revvs`
   - 基础名称：`voice_message_commander_move_revvs`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_move_revvs_v1`
     - `voice_message_commander_move_revvs_v2`
     - `voice_message_commander_move_revvs_v3`

30. `voice_message_commander_move_slower`

   - 组键：`voice_message_commander_move_slower`
   - 基础名称：`voice_message_commander_move_slower`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_move_slower_v1`
     - `voice_message_commander_move_slower_v2`
     - `voice_message_commander_move_slower_v3`

31. `voice_message_commander_move_stop`

   - 组键：`voice_message_commander_move_stop`
   - 基础名称：`voice_message_commander_move_stop`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_move_stop_v1`
     - `voice_message_commander_move_stop_v2`
     - `voice_message_commander_move_stop_v3`

32. `voice_message_commander_reload`

   - 组键：`voice_message_commander_reload`
   - 基础名称：`voice_message_commander_reload`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_reload_v1`
     - `voice_message_commander_reload_v2`
     - `voice_message_commander_reload_v3`

33. `voice_message_commander_repair_needed`

   - 组键：`voice_message_commander_repair_needed`
   - 基础名称：`voice_message_commander_repair_needed`
   - 命名类型：`single`
   - 成员数量：4
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_repair_needed_v1`
     - `voice_message_commander_repair_needed_v2`
     - `voice_message_commander_repair_needed_v3`
     - `voice_message_commander_repair_needed_v4`

34. `voice_message_commander_shot`

   - 组键：`voice_message_commander_shot`
   - 基础名称：`voice_message_commander_shot`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_shot_v1`
     - `voice_message_commander_shot_v2`
     - `voice_message_commander_shot_v3`

35. `voice_message_commander_shovel_off`

   - 组键：`voice_message_commander_shovel_off`
   - 基础名称：`voice_message_commander_shovel_off`
   - 命名类型：`double`
   - 成员数量：2
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_shovel_off_v2_2`
     - `voice_message_commander_shovel_off_v2_3`

36. `voice_message_commander_shovel_on`

   - 组键：`voice_message_commander_shovel_on`
   - 基础名称：`voice_message_commander_shovel_on`
   - 命名类型：`double`
   - 成员数量：4
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_shovel_on_v1_1`
     - `voice_message_commander_shovel_on_v1_2`
     - `voice_message_commander_shovel_on_v1_3`
     - `voice_message_commander_shovel_on_v2_1`

37. `voice_message_commander_stabilizer_off`

   - 组键：`voice_message_commander_stabilizer_off`
   - 基础名称：`voice_message_commander_stabilizer_off`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_stabilizer_off_v1`
     - `voice_message_commander_stabilizer_off_v2`
     - `voice_message_commander_stabilizer_off_v3`

38. `voice_message_commander_stabilizer_on`

   - 组键：`voice_message_commander_stabilizer_on`
   - 基础名称：`voice_message_commander_stabilizer_on`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_stabilizer_on_v1`
     - `voice_message_commander_stabilizer_on_v2`
     - `voice_message_commander_stabilizer_on_v3`

39. `voice_message_commander_target_distance`

   - 组键：`voice_message_commander_target_distance`
   - 基础名称：`voice_message_commander_target_distance`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_target_distance_v1`
     - `voice_message_commander_target_distance_v2`
     - `voice_message_commander_target_distance_v3`

40. `voice_message_commander_target_near`

   - 组键：`voice_message_commander_target_near`
   - 基础名称：`voice_message_commander_target_near`
   - 命名类型：`double`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_target_near_v1_1`
     - `voice_message_commander_target_near_v1_2`
     - `voice_message_commander_target_near_v1_3`
     - `voice_message_commander_target_near_v2_1`
     - `voice_message_commander_target_near_v2_2`
     - `voice_message_commander_target_near_v2_3`

41. `voice_message_commander_target_on_the_move`

   - 组键：`voice_message_commander_target_on_the_move`
   - 基础名称：`voice_message_commander_target_on_the_move`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_target_on_the_move_v1`
     - `voice_message_commander_target_on_the_move_v2`
     - `voice_message_commander_target_on_the_move_v3`

42. `voice_message_commander_ucav_launch`

   - 组键：`voice_message_commander_ucav_launch`
   - 基础名称：`voice_message_commander_ucav_launch`
   - 命名类型：`mixed`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_ucav_launch_v1_1`
     - `voice_message_commander_ucav_launch_v1_2`
     - `voice_message_commander_ucav_launch_v1_3`
     - `voice_message_commander_ucav_launch_v2`
     - `voice_message_commander_ucav_launch_v3`
     - `voice_message_commander_ucav_launch_v4`

43. `voice_message_commander_ucav_recover`

   - 组键：`voice_message_commander_ucav_recover`
   - 基础名称：`voice_message_commander_ucav_recover`
   - 命名类型：`mixed`
   - 成员数量：4
   - `module`：`crew`
   - `category`：`commander`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_ucav_recover_v1_1`
     - `voice_message_commander_ucav_recover_v1_2`
     - `voice_message_commander_ucav_recover_v1_3`
     - `voice_message_commander_ucav_recover_v2`

### 3.5 driver

1. `voice_message_driver_armor_breached`

   - 组键：`voice_message_driver_armor_breached`
   - 基础名称：`voice_message_driver_armor_breached`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_armor_breached_v1`
     - `voice_message_driver_armor_breached_v2`
     - `voice_message_driver_armor_breached_v3`

2. `voice_message_driver_battle_ready`

   - 组键：`voice_message_driver_battle_ready`
   - 基础名称：`voice_message_driver_battle_ready`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_battle_ready_v1`
     - `voice_message_driver_battle_ready_v2`
     - `voice_message_driver_battle_ready_v3`

3. `voice_message_driver_correction_bracketed`

   - 组键：`voice_message_driver_correction_bracketed`
   - 基础名称：`voice_message_driver_correction_bracketed`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_correction_bracketed_v1`
     - `voice_message_driver_correction_bracketed_v2`
     - `voice_message_driver_correction_bracketed_v3`

4. `voice_message_driver_correction_hit`

   - 组键：`voice_message_driver_correction_hit`
   - 基础名称：`voice_message_driver_correction_hit`
   - 命名类型：`single`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_correction_hit_v1`
     - `voice_message_driver_correction_hit_v2`
     - `voice_message_driver_correction_hit_v3`
     - `voice_message_driver_correction_hit_v4`
     - `voice_message_driver_correction_hit_v5`
     - `voice_message_driver_correction_hit_v6`

5. `voice_message_driver_correction_left`

   - 组键：`voice_message_driver_correction_left`
   - 基础名称：`voice_message_driver_correction_left`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_correction_left_v1`
     - `voice_message_driver_correction_left_v2`
     - `voice_message_driver_correction_left_v3`

6. `voice_message_driver_correction_retreat`

   - 组键：`voice_message_driver_correction_retreat`
   - 基础名称：`voice_message_driver_correction_retreat`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_correction_retreat_v1`
     - `voice_message_driver_correction_retreat_v2`
     - `voice_message_driver_correction_retreat_v3`

7. `voice_message_driver_correction_right`

   - 组键：`voice_message_driver_correction_right`
   - 基础名称：`voice_message_driver_correction_right`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_correction_right_v1`
     - `voice_message_driver_correction_right_v2`
     - `voice_message_driver_correction_right_v3`

8. `voice_message_driver_correction_target_destroyed_revenge`

   - 组键：`voice_message_driver_correction_target_destroyed_revenge`
   - 基础名称：`voice_message_driver_correction_target_destroyed_revenge`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_correction_target_destroyed_revenge_v1`
     - `voice_message_driver_correction_target_destroyed_revenge_v2`
     - `voice_message_driver_correction_target_destroyed_revenge_v3`

9. `voice_message_driver_correction_target_hit`

   - 组键：`voice_message_driver_correction_target_hit`
   - 基础名称：`voice_message_driver_correction_target_hit`
   - 命名类型：`single`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_correction_target_hit_v1`
     - `voice_message_driver_correction_target_hit_v2`
     - `voice_message_driver_correction_target_hit_v3`
     - `voice_message_driver_correction_target_hit_v4`
     - `voice_message_driver_correction_target_hit_v5`
     - `voice_message_driver_correction_target_hit_v6`

10. `voice_message_driver_correction_undershoot`

   - 组键：`voice_message_driver_correction_undershoot`
   - 基础名称：`voice_message_driver_correction_undershoot`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_correction_undershoot_v1`
     - `voice_message_driver_correction_undershoot_v2`
     - `voice_message_driver_correction_undershoot_v3`

11. `voice_message_driver_damaged`

   - 组键：`voice_message_driver_damaged`
   - 基础名称：`voice_message_driver_damaged`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_damaged_v1`
     - `voice_message_driver_damaged_v2`
     - `voice_message_driver_damaged_v3`

12. `voice_message_driver_engine_fuel_leak`

   - 组键：`voice_message_driver_engine_fuel_leak`
   - 基础名称：`voice_message_driver_engine_fuel_leak`
   - 命名类型：`double`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_engine_fuel_leak_v1_1`
     - `voice_message_driver_engine_fuel_leak_v1_2`
     - `voice_message_driver_engine_fuel_leak_v1_3`
     - `voice_message_driver_engine_fuel_leak_v2_1`
     - `voice_message_driver_engine_fuel_leak_v2_2`
     - `voice_message_driver_engine_fuel_leak_v2_3`

13. `voice_message_driver_engine_ready`

   - 组键：`voice_message_driver_engine_ready`
   - 基础名称：`voice_message_driver_engine_ready`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_engine_ready_v1`
     - `voice_message_driver_engine_ready_v2`
     - `voice_message_driver_engine_ready_v3`

14. `voice_message_driver_engine_repaired`

   - 组键：`voice_message_driver_engine_repaired`
   - 基础名称：`voice_message_driver_engine_repaired`
   - 命名类型：`double`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_engine_repaired_v1_1`
     - `voice_message_driver_engine_repaired_v1_2`
     - `voice_message_driver_engine_repaired_v1_3`
     - `voice_message_driver_engine_repaired_v2_1`
     - `voice_message_driver_engine_repaired_v2_2`
     - `voice_message_driver_engine_repaired_v2_3`

15. `voice_message_driver_fire`

   - 组键：`voice_message_driver_fire`
   - 基础名称：`voice_message_driver_fire`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_fire_v1`
     - `voice_message_driver_fire_v2`
     - `voice_message_driver_fire_v3`

16. `voice_message_driver_fire_engine`

   - 组键：`voice_message_driver_fire_engine`
   - 基础名称：`voice_message_driver_fire_engine`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_fire_engine_v1`
     - `voice_message_driver_fire_engine_v2`
     - `voice_message_driver_fire_engine_v3`

17. `voice_message_driver_fire_extinguished`

   - 组键：`voice_message_driver_fire_extinguished`
   - 基础名称：`voice_message_driver_fire_extinguished`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_fire_extinguished_v1`
     - `voice_message_driver_fire_extinguished_v2`
     - `voice_message_driver_fire_extinguished_v3`

18. `voice_message_driver_fire_fighting_compartment`

   - 组键：`voice_message_driver_fire_fighting_compartment`
   - 基础名称：`voice_message_driver_fire_fighting_compartment`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_fire_fighting_compartment_v1`
     - `voice_message_driver_fire_fighting_compartment_v2`
     - `voice_message_driver_fire_fighting_compartment_v3`

19. `voice_message_driver_fire_munition_compartment`

   - 组键：`voice_message_driver_fire_munition_compartment`
   - 基础名称：`voice_message_driver_fire_munition_compartment`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_fire_munition_compartment_v1`
     - `voice_message_driver_fire_munition_compartment_v2`
     - `voice_message_driver_fire_munition_compartment_v3`

20. `voice_message_driver_gunner_stunned`

   - 组键：`voice_message_driver_gunner_stunned`
   - 基础名称：`voice_message_driver_gunner_stunned`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_gunner_stunned_v1`
     - `voice_message_driver_gunner_stunned_v2`
     - `voice_message_driver_gunner_stunned_v3`

21. `voice_message_driver_gunner_unconscious`

   - 组键：`voice_message_driver_gunner_unconscious`
   - 基础名称：`voice_message_driver_gunner_unconscious`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_gunner_unconscious_v1`
     - `voice_message_driver_gunner_unconscious_v2`
     - `voice_message_driver_gunner_unconscious_v3`

22. `voice_message_driver_left_track`

   - 组键：`voice_message_driver_left_track`
   - 基础名称：`voice_message_driver_left_track`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_left_track_v1`
     - `voice_message_driver_left_track_v2`
     - `voice_message_driver_left_track_v3`

23. `voice_message_driver_loader_stunned`

   - 组键：`voice_message_driver_loader_stunned`
   - 基础名称：`voice_message_driver_loader_stunned`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_loader_stunned_v1`
     - `voice_message_driver_loader_stunned_v2`
     - `voice_message_driver_loader_stunned_v3`

24. `voice_message_driver_loader_unconscious`

   - 组键：`voice_message_driver_loader_unconscious`
   - 基础名称：`voice_message_driver_loader_unconscious`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_loader_unconscious_v1`
     - `voice_message_driver_loader_unconscious_v2`
     - `voice_message_driver_loader_unconscious_v3`

25. `voice_message_driver_move_forward`

   - 组键：`voice_message_driver_move_forward`
   - 基础名称：`voice_message_driver_move_forward`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_move_forward_v1`
     - `voice_message_driver_move_forward_v2`
     - `voice_message_driver_move_forward_v3`

26. `voice_message_driver_obstacle`

   - 组键：`voice_message_driver_obstacle`
   - 基础名称：`voice_message_driver_obstacle`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_obstacle_v1`
     - `voice_message_driver_obstacle_v2`
     - `voice_message_driver_obstacle_v3`

27. `voice_message_driver_on_the_move`

   - 组键：`voice_message_driver_on_the_move`
   - 基础名称：`voice_message_driver_on_the_move`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_on_the_move_v1`
     - `voice_message_driver_on_the_move_v2`
     - `voice_message_driver_on_the_move_v3`

28. `voice_message_driver_radiator_damaged`

   - 组键：`voice_message_driver_radiator_damaged`
   - 基础名称：`voice_message_driver_radiator_damaged`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_radiator_damaged_v1`
     - `voice_message_driver_radiator_damaged_v2`
     - `voice_message_driver_radiator_damaged_v3`

29. `voice_message_driver_right_track`

   - 组键：`voice_message_driver_right_track`
   - 基础名称：`voice_message_driver_right_track`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_right_track_v1`
     - `voice_message_driver_right_track_v2`
     - `voice_message_driver_right_track_v3`

30. `voice_message_driver_running_gear_damaged`

   - 组键：`voice_message_driver_running_gear_damaged`
   - 基础名称：`voice_message_driver_running_gear_damaged`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_running_gear_damaged_v1`
     - `voice_message_driver_running_gear_damaged_v2`
     - `voice_message_driver_running_gear_damaged_v3`

31. `voice_message_driver_taking_command`

   - 组键：`voice_message_driver_taking_command`
   - 基础名称：`voice_message_driver_taking_command`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_taking_command_v1`
     - `voice_message_driver_taking_command_v2`
     - `voice_message_driver_taking_command_v3`

32. `voice_message_driver_track_lost`

   - 组键：`voice_message_driver_track_lost`
   - 基础名称：`voice_message_driver_track_lost`
   - 命名类型：`double`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_track_lost_v1_1`
     - `voice_message_driver_track_lost_v1_2`
     - `voice_message_driver_track_lost_v1_3`
     - `voice_message_driver_track_lost_v2_1`
     - `voice_message_driver_track_lost_v2_2`
     - `voice_message_driver_track_lost_v2_3`

33. `voice_message_driver_tracks_repaired`

   - 组键：`voice_message_driver_tracks_repaired`
   - 基础名称：`voice_message_driver_tracks_repaired`
   - 命名类型：`double`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_tracks_repaired_v1_1`
     - `voice_message_driver_tracks_repaired_v1_2`
     - `voice_message_driver_tracks_repaired_v1_3`
     - `voice_message_driver_tracks_repaired_v2_1`
     - `voice_message_driver_tracks_repaired_v2_2`
     - `voice_message_driver_tracks_repaired_v2_3`

34. `voice_message_driver_transmission_damaged`

   - 组键：`voice_message_driver_transmission_damaged`
   - 基础名称：`voice_message_driver_transmission_damaged`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_transmission_damaged_v1`
     - `voice_message_driver_transmission_damaged_v2`
     - `voice_message_driver_transmission_damaged_v3`

35. `voice_message_driver_turning_left`

   - 组键：`voice_message_driver_turning_left`
   - 基础名称：`voice_message_driver_turning_left`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_turning_left_v1`
     - `voice_message_driver_turning_left_v2`
     - `voice_message_driver_turning_left_v3`

36. `voice_message_driver_turning_right`

   - 组键：`voice_message_driver_turning_right`
   - 基础名称：`voice_message_driver_turning_right`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_turning_right_v1`
     - `voice_message_driver_turning_right_v2`
     - `voice_message_driver_turning_right_v3`

37. `voice_message_driver_weve_been_hit`

   - 组键：`voice_message_driver_weve_been_hit`
   - 基础名称：`voice_message_driver_weve_been_hit`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_weve_been_hit_v1`
     - `voice_message_driver_weve_been_hit_v2`
     - `voice_message_driver_weve_been_hit_v3`

38. `voice_message_driver_wheel_lost`

   - 组键：`voice_message_driver_wheel_lost`
   - 基础名称：`voice_message_driver_wheel_lost`
   - 命名类型：`double`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_wheel_lost_v1_1`
     - `voice_message_driver_wheel_lost_v1_2`
     - `voice_message_driver_wheel_lost_v1_3`
     - `voice_message_driver_wheel_lost_v2_1`
     - `voice_message_driver_wheel_lost_v2_2`
     - `voice_message_driver_wheel_lost_v2_3`

39. `voice_message_driver_wheel_repaired`

   - 组键：`voice_message_driver_wheel_repaired`
   - 基础名称：`voice_message_driver_wheel_repaired`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_wheel_repaired_v1`
     - `voice_message_driver_wheel_repaired_v2`
     - `voice_message_driver_wheel_repaired_v3`

40. `voice_message_driver_engine_stalled`

   - 组键：`voice_message_driver_engine_stalled__v1_layers`
   - 基础名称：`voice_message_driver_engine_stalled`
   - 命名类型：`double`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_engine_stalled_v1_1`
     - `voice_message_driver_engine_stalled_v1_2`
     - `voice_message_driver_engine_stalled_v1_3`

41. `voice_message_driver_engine_stalled`

   - 组键：`voice_message_driver_engine_stalled__v2_v3`
   - 基础名称：`voice_message_driver_engine_stalled`
   - 命名类型：`single`
   - 成员数量：2
   - `module`：`crew`
   - `category`：`driver`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_driver_engine_stalled_v2`
     - `voice_message_driver_engine_stalled_v3`

### 3.6 gunner

1. `voice_message_gunner_armor_breached`

   - 组键：`voice_message_gunner_armor_breached`
   - 基础名称：`voice_message_gunner_armor_breached`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_armor_breached_v1`
     - `voice_message_gunner_armor_breached_v2`
     - `voice_message_gunner_armor_breached_v3`

2. `voice_message_gunner_barrel_damaged`

   - 组键：`voice_message_gunner_barrel_damaged`
   - 基础名称：`voice_message_gunner_barrel_damaged`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_barrel_damaged_v1`
     - `voice_message_gunner_barrel_damaged_v2`
     - `voice_message_gunner_barrel_damaged_v3`

3. `voice_message_gunner_battle_ready`

   - 组键：`voice_message_gunner_battle_ready`
   - 基础名称：`voice_message_gunner_battle_ready`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_battle_ready_v1`
     - `voice_message_gunner_battle_ready_v2`
     - `voice_message_gunner_battle_ready_v3`

4. `voice_message_gunner_breech_damaged`

   - 组键：`voice_message_gunner_breech_damaged`
   - 基础名称：`voice_message_gunner_breech_damaged`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_breech_damaged_v1`
     - `voice_message_gunner_breech_damaged_v2`
     - `voice_message_gunner_breech_damaged_v3`

5. `voice_message_gunner_cannon_drives_repaired`

   - 组键：`voice_message_gunner_cannon_drives_repaired`
   - 基础名称：`voice_message_gunner_cannon_drives_repaired`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_cannon_drives_repaired_v1`
     - `voice_message_gunner_cannon_drives_repaired_v2`
     - `voice_message_gunner_cannon_drives_repaired_v3`

6. `voice_message_gunner_cannon_ready`

   - 组键：`voice_message_gunner_cannon_ready`
   - 基础名称：`voice_message_gunner_cannon_ready`
   - 命名类型：`double`
   - 成员数量：6
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_cannon_ready_v1_1`
     - `voice_message_gunner_cannon_ready_v1_2`
     - `voice_message_gunner_cannon_ready_v1_3`
     - `voice_message_gunner_cannon_ready_v2_1`
     - `voice_message_gunner_cannon_ready_v2_2`
     - `voice_message_gunner_cannon_ready_v2_3`

7. `voice_message_gunner_damaged`

   - 组键：`voice_message_gunner_damaged`
   - 基础名称：`voice_message_gunner_damaged`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_damaged_v1`
     - `voice_message_gunner_damaged_v2`
     - `voice_message_gunner_damaged_v3`

8. `voice_message_gunner_driver_stunned`

   - 组键：`voice_message_gunner_driver_stunned`
   - 基础名称：`voice_message_gunner_driver_stunned`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_driver_stunned_v1`
     - `voice_message_gunner_driver_stunned_v2`
     - `voice_message_gunner_driver_stunned_v3`

9. `voice_message_gunner_driver_unconscious`

   - 组键：`voice_message_gunner_driver_unconscious`
   - 基础名称：`voice_message_gunner_driver_unconscious`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_driver_unconscious_v1`
     - `voice_message_gunner_driver_unconscious_v2`
     - `voice_message_gunner_driver_unconscious_v3`

10. `voice_message_gunner_elevation_drive_damaged`

   - 组键：`voice_message_gunner_elevation_drive_damaged`
   - 基础名称：`voice_message_gunner_elevation_drive_damaged`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_elevation_drive_damaged_v1`
     - `voice_message_gunner_elevation_drive_damaged_v2`
     - `voice_message_gunner_elevation_drive_damaged_v3`

11. `voice_message_gunner_elevation_drive_repaired`

   - 组键：`voice_message_gunner_elevation_drive_repaired`
   - 基础名称：`voice_message_gunner_elevation_drive_repaired`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_elevation_drive_repaired_v1`
     - `voice_message_gunner_elevation_drive_repaired_v2`
     - `voice_message_gunner_elevation_drive_repaired_v3`

12. `voice_message_gunner_fire`

   - 组键：`voice_message_gunner_fire`
   - 基础名称：`voice_message_gunner_fire`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_fire_v1`
     - `voice_message_gunner_fire_v2`
     - `voice_message_gunner_fire_v3`

13. `voice_message_gunner_fire_engine`

   - 组键：`voice_message_gunner_fire_engine`
   - 基础名称：`voice_message_gunner_fire_engine`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_fire_engine_v1`
     - `voice_message_gunner_fire_engine_v2`
     - `voice_message_gunner_fire_engine_v3`

14. `voice_message_gunner_fire_extinguished`

   - 组键：`voice_message_gunner_fire_extinguished`
   - 基础名称：`voice_message_gunner_fire_extinguished`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_fire_extinguished_v1`
     - `voice_message_gunner_fire_extinguished_v2`
     - `voice_message_gunner_fire_extinguished_v3`

15. `voice_message_gunner_fire_fighting_compartment`

   - 组键：`voice_message_gunner_fire_fighting_compartment`
   - 基础名称：`voice_message_gunner_fire_fighting_compartment`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_fire_fighting_compartment_v1`
     - `voice_message_gunner_fire_fighting_compartment_v2`
     - `voice_message_gunner_fire_fighting_compartment_v3`

16. `voice_message_gunner_fire_munition_compartment`

   - 组键：`voice_message_gunner_fire_munition_compartment`
   - 基础名称：`voice_message_gunner_fire_munition_compartment`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_fire_munition_compartment_v1`
     - `voice_message_gunner_fire_munition_compartment_v2`
     - `voice_message_gunner_fire_munition_compartment_v3`

17. `voice_message_gunner_loader_stunned`

   - 组键：`voice_message_gunner_loader_stunned`
   - 基础名称：`voice_message_gunner_loader_stunned`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_loader_stunned_v1`
     - `voice_message_gunner_loader_stunned_v2`
     - `voice_message_gunner_loader_stunned_v3`

18. `voice_message_gunner_loader_unconscious`

   - 组键：`voice_message_gunner_loader_unconscious`
   - 基础名称：`voice_message_gunner_loader_unconscious`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_loader_unconscious_v1`
     - `voice_message_gunner_loader_unconscious_v2`
     - `voice_message_gunner_loader_unconscious_v3`

19. `voice_message_gunner_mg_aa_lost`

   - 组键：`voice_message_gunner_mg_aa_lost`
   - 基础名称：`voice_message_gunner_mg_aa_lost`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_mg_aa_lost_v1`
     - `voice_message_gunner_mg_aa_lost_v2`
     - `voice_message_gunner_mg_aa_lost_v3`

20. `voice_message_gunner_mg_directional_lost`

   - 组键：`voice_message_gunner_mg_directional_lost`
   - 基础名称：`voice_message_gunner_mg_directional_lost`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_mg_directional_lost_v1`
     - `voice_message_gunner_mg_directional_lost_v2`
     - `voice_message_gunner_mg_directional_lost_v3`

21. `voice_message_gunner_mg_ready`

   - 组键：`voice_message_gunner_mg_ready`
   - 基础名称：`voice_message_gunner_mg_ready`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_mg_ready_v1`
     - `voice_message_gunner_mg_ready_v2`
     - `voice_message_gunner_mg_ready_v3`

22. `voice_message_gunner_misfire`

   - 组键：`voice_message_gunner_misfire`
   - 基础名称：`voice_message_gunner_misfire`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_misfire_v1`
     - `voice_message_gunner_misfire_v2`
     - `voice_message_gunner_misfire_v3`

23. `voice_message_gunner_rotation_drive_damaged`

   - 组键：`voice_message_gunner_rotation_drive_damaged`
   - 基础名称：`voice_message_gunner_rotation_drive_damaged`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_rotation_drive_damaged_v1`
     - `voice_message_gunner_rotation_drive_damaged_v2`
     - `voice_message_gunner_rotation_drive_damaged_v3`

24. `voice_message_gunner_rotation_drive_repaired`

   - 组键：`voice_message_gunner_rotation_drive_repaired`
   - 基础名称：`voice_message_gunner_rotation_drive_repaired`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_rotation_drive_repaired_v1`
     - `voice_message_gunner_rotation_drive_repaired_v2`
     - `voice_message_gunner_rotation_drive_repaired_v3`

25. `voice_message_gunner_shot`

   - 组键：`voice_message_gunner_shot`
   - 基础名称：`voice_message_gunner_shot`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_shot_v1`
     - `voice_message_gunner_shot_v2`
     - `voice_message_gunner_shot_v3`

26. `voice_message_gunner_taking_command`

   - 组键：`voice_message_gunner_taking_command`
   - 基础名称：`voice_message_gunner_taking_command`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_taking_command_v1`
     - `voice_message_gunner_taking_command_v2`
     - `voice_message_gunner_taking_command_v3`

27. `voice_message_gunner_turret_left`

   - 组键：`voice_message_gunner_turret_left`
   - 基础名称：`voice_message_gunner_turret_left`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_turret_left_v1`
     - `voice_message_gunner_turret_left_v2`
     - `voice_message_gunner_turret_left_v3`

28. `voice_message_gunner_turret_right`

   - 组键：`voice_message_gunner_turret_right`
   - 基础名称：`voice_message_gunner_turret_right`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_turret_right_v1`
     - `voice_message_gunner_turret_right_v2`
     - `voice_message_gunner_turret_right_v3`

29. `voice_message_gunner_weve_been_hit`

   - 组键：`voice_message_gunner_weve_been_hit`
   - 基础名称：`voice_message_gunner_weve_been_hit`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`gunner`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_gunner_weve_been_hit_v1`
     - `voice_message_gunner_weve_been_hit_v2`
     - `voice_message_gunner_weve_been_hit_v3`

### 3.7 loader

1. `voice_message_loader_armor_breached`

   - 组键：`voice_message_loader_armor_breached`
   - 基础名称：`voice_message_loader_armor_breached`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_armor_breached_v1`
     - `voice_message_loader_armor_breached_v2`
     - `voice_message_loader_armor_breached_v3`

2. `voice_message_loader_battle_ready`

   - 组键：`voice_message_loader_battle_ready`
   - 基础名称：`voice_message_loader_battle_ready`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_battle_ready_v1`
     - `voice_message_loader_battle_ready_v2`
     - `voice_message_loader_battle_ready_v3`

3. `voice_message_loader_damaged`

   - 组键：`voice_message_loader_damaged`
   - 基础名称：`voice_message_loader_damaged`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_damaged_v1`
     - `voice_message_loader_damaged_v2`
     - `voice_message_loader_damaged_v3`

4. `voice_message_loader_driver_stunned`

   - 组键：`voice_message_loader_driver_stunned`
   - 基础名称：`voice_message_loader_driver_stunned`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_driver_stunned_v1`
     - `voice_message_loader_driver_stunned_v2`
     - `voice_message_loader_driver_stunned_v3`

5. `voice_message_loader_driver_unconscious`

   - 组键：`voice_message_loader_driver_unconscious`
   - 基础名称：`voice_message_loader_driver_unconscious`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_driver_unconscious_v1`
     - `voice_message_loader_driver_unconscious_v2`
     - `voice_message_loader_driver_unconscious_v3`

6. `voice_message_loader_fire`

   - 组键：`voice_message_loader_fire`
   - 基础名称：`voice_message_loader_fire`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_fire_v1`
     - `voice_message_loader_fire_v2`
     - `voice_message_loader_fire_v3`

7. `voice_message_loader_fire_engine`

   - 组键：`voice_message_loader_fire_engine`
   - 基础名称：`voice_message_loader_fire_engine`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_fire_engine_v1`
     - `voice_message_loader_fire_engine_v2`
     - `voice_message_loader_fire_engine_v3`

8. `voice_message_loader_fire_extinguished`

   - 组键：`voice_message_loader_fire_extinguished`
   - 基础名称：`voice_message_loader_fire_extinguished`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_fire_extinguished_v1`
     - `voice_message_loader_fire_extinguished_v2`
     - `voice_message_loader_fire_extinguished_v3`

9. `voice_message_loader_fire_fighting_compartment`

   - 组键：`voice_message_loader_fire_fighting_compartment`
   - 基础名称：`voice_message_loader_fire_fighting_compartment`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_fire_fighting_compartment_v1`
     - `voice_message_loader_fire_fighting_compartment_v2`
     - `voice_message_loader_fire_fighting_compartment_v3`

10. `voice_message_loader_fire_munition_compartment`

   - 组键：`voice_message_loader_fire_munition_compartment`
   - 基础名称：`voice_message_loader_fire_munition_compartment`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_fire_munition_compartment_v1`
     - `voice_message_loader_fire_munition_compartment_v2`
     - `voice_message_loader_fire_munition_compartment_v3`

11. `voice_message_loader_gunner_stunned`

   - 组键：`voice_message_loader_gunner_stunned`
   - 基础名称：`voice_message_loader_gunner_stunned`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_gunner_stunned_v1`
     - `voice_message_loader_gunner_stunned_v2`
     - `voice_message_loader_gunner_stunned_v3`

12. `voice_message_loader_gunner_unconscious`

   - 组键：`voice_message_loader_gunner_unconscious`
   - 基础名称：`voice_message_loader_gunner_unconscious`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_gunner_unconscious_v1`
     - `voice_message_loader_gunner_unconscious_v2`
     - `voice_message_loader_gunner_unconscious_v3`

13. `voice_message_loader_load_AP`

   - 组键：`voice_message_loader_load_AP`
   - 基础名称：`voice_message_loader_load_AP`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_load_AP_v1`
     - `voice_message_loader_load_AP_v2`
     - `voice_message_loader_load_AP_v3`

14. `voice_message_loader_load_HE`

   - 组键：`voice_message_loader_load_HE`
   - 基础名称：`voice_message_loader_load_HE`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_load_HE_v1`
     - `voice_message_loader_load_HE_v2`
     - `voice_message_loader_load_HE_v3`

15. `voice_message_loader_load_HEAT`

   - 组键：`voice_message_loader_load_HEAT`
   - 基础名称：`voice_message_loader_load_HEAT`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_load_HEAT_v1`
     - `voice_message_loader_load_HEAT_v2`
     - `voice_message_loader_load_HEAT_v3`

16. `voice_message_loader_load_HESH`

   - 组键：`voice_message_loader_load_HESH`
   - 基础名称：`voice_message_loader_load_HESH`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_load_HESH_v1`
     - `voice_message_loader_load_HESH_v2`
     - `voice_message_loader_load_HESH_v3`

17. `voice_message_loader_load_canister`

   - 组键：`voice_message_loader_load_canister`
   - 基础名称：`voice_message_loader_load_canister`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_load_canister_v1`
     - `voice_message_loader_load_canister_v2`
     - `voice_message_loader_load_canister_v3`

18. `voice_message_loader_load_flares`

   - 组键：`voice_message_loader_load_flares`
   - 基础名称：`voice_message_loader_load_flares`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_load_flares_v1`
     - `voice_message_loader_load_flares_v2`
     - `voice_message_loader_load_flares_v3`

19. `voice_message_loader_load_frag`

   - 组键：`voice_message_loader_load_frag`
   - 基础名称：`voice_message_loader_load_frag`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_load_frag_v1`
     - `voice_message_loader_load_frag_v2`
     - `voice_message_loader_load_frag_v3`

20. `voice_message_loader_load_missile`

   - 组键：`voice_message_loader_load_missile`
   - 基础名称：`voice_message_loader_load_missile`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_load_missile_v1`
     - `voice_message_loader_load_missile_v2`
     - `voice_message_loader_load_missile_v3`

21. `voice_message_loader_load_sabot`

   - 组键：`voice_message_loader_load_sabot`
   - 基础名称：`voice_message_loader_load_sabot`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_load_sabot_v1`
     - `voice_message_loader_load_sabot_v2`
     - `voice_message_loader_load_sabot_v3`

22. `voice_message_loader_load_smoke`

   - 组键：`voice_message_loader_load_smoke`
   - 基础名称：`voice_message_loader_load_smoke`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_load_smoke_v1`
     - `voice_message_loader_load_smoke_v2`
     - `voice_message_loader_load_smoke_v3`

23. `voice_message_loader_mg_ready`

   - 组键：`voice_message_loader_mg_ready`
   - 基础名称：`voice_message_loader_mg_ready`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_mg_ready_v1`
     - `voice_message_loader_mg_ready_v2`
     - `voice_message_loader_mg_ready_v3`

24. `voice_message_loader_taking_command`

   - 组键：`voice_message_loader_taking_command`
   - 基础名称：`voice_message_loader_taking_command`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_taking_command_v1`
     - `voice_message_loader_taking_command_v2`
     - `voice_message_loader_taking_command_v3`

25. `voice_message_loader_weve_been_hit`

   - 组键：`voice_message_loader_weve_been_hit`
   - 基础名称：`voice_message_loader_weve_been_hit`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：`loader`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_loader_weve_been_hit_v1`
     - `voice_message_loader_weve_been_hit_v2`
     - `voice_message_loader_weve_been_hit_v3`

### 3.8 未分类项目组

> 以下组缺少 `category` 字段；程序仍能按完整名称查到它们，但语音处理页不能自动切换到确定分类。

1. `voice_message_commander_night_vision_off`

   - 组键：`voice_message_commander_night_vision_off`
   - 基础名称：`voice_message_commander_night_vision_off`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_night_vision_off_v1`
     - `voice_message_commander_night_vision_off_v2`
     - `voice_message_commander_night_vision_off_v3`

2. `voice_message_commander_night_vision_on`

   - 组键：`voice_message_commander_night_vision_on`
   - 基础名称：`voice_message_commander_night_vision_on`
   - 命名类型：`single`
   - 成员数量：3
   - `module`：`crew`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_night_vision_on_v1`
     - `voice_message_commander_night_vision_on_v2`
     - `voice_message_commander_night_vision_on_v3`

3. `voice_message_commander_target_prem`

   - 组键：`voice_message_commander_target_prem`
   - 基础名称：`voice_message_commander_target_prem`
   - 命名类型：`single`
   - 成员数量：2
   - `module`：`crew`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_commander_target_prem_v1`
     - `voice_message_commander_target_prem_v2`

## 4. 无线电完整分组

### 4.1 根对象元数据

- `schema_version`：`1`
- `module`：`radio`
- `source_directories`（仅供数据审计，程序运行不依赖）：
  - `<external-radio-source:voice1>`
  - `<external-radio-source:additional_01>`
  - `<external-radio-source:english>`
- 其他根字段：无

### 4.2 态势播报

1. `pilot_capture_gm_ally`

   - 组键：`pilot_capture_gm_ally`
   - 基础名称：`pilot_capture_gm_ally`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`态势播报`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_capture_gm_ally_v1`
     - `pilot_capture_gm_ally_v2`
     - `pilot_capture_gm_ally_v3`
   - 来源字段：
     - `pilot_capture_gm_ally_v1`：`["english"]`
     - `pilot_capture_gm_ally_v2`：`["english"]`
     - `pilot_capture_gm_ally_v3`：`["english"]`

2. `pilot_capture_gm_enemy`

   - 组键：`pilot_capture_gm_enemy`
   - 基础名称：`pilot_capture_gm_enemy`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`态势播报`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_capture_gm_enemy_v1`
     - `pilot_capture_gm_enemy_v2`
     - `pilot_capture_gm_enemy_v3`
   - 来源字段：
     - `pilot_capture_gm_enemy_v1`：`["english"]`
     - `pilot_capture_gm_enemy_v2`：`["english"]`
     - `pilot_capture_gm_enemy_v3`：`["english"]`

3. `pilot_capture_zone_ally`

   - 组键：`pilot_capture_zone_ally`
   - 基础名称：`pilot_capture_zone_ally`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`态势播报`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_capture_zone_ally_v1`
     - `pilot_capture_zone_ally_v2`
     - `pilot_capture_zone_ally_v3`
   - 来源字段：
     - `pilot_capture_zone_ally_v1`：`["english"]`
     - `pilot_capture_zone_ally_v2`：`["english"]`
     - `pilot_capture_zone_ally_v3`：`["english"]`

4. `pilot_capture_zone_enemy`

   - 组键：`pilot_capture_zone_enemy`
   - 基础名称：`pilot_capture_zone_enemy`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`态势播报`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_capture_zone_enemy_v1`
     - `pilot_capture_zone_enemy_v2`
     - `pilot_capture_zone_enemy_v3`
   - 来源字段：
     - `pilot_capture_zone_enemy_v1`：`["english"]`
     - `pilot_capture_zone_enemy_v2`：`["english"]`
     - `pilot_capture_zone_enemy_v3`：`["english"]`

5. `pilot_tickets_lead_continue_ally`

   - 组键：`pilot_tickets_lead_continue_ally`
   - 基础名称：`pilot_tickets_lead_continue_ally`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：`态势播报`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_tickets_lead_continue_ally_1_v1`
     - `pilot_tickets_lead_continue_ally_1_v2`
     - `pilot_tickets_lead_continue_ally_1_v3`
     - `pilot_tickets_lead_continue_ally_2_v1`
     - `pilot_tickets_lead_continue_ally_2_v2`
     - `pilot_tickets_lead_continue_ally_2_v3`
     - `pilot_tickets_lead_continue_ally_3_v1`
     - `pilot_tickets_lead_continue_ally_3_v2`
     - `pilot_tickets_lead_continue_ally_3_v3`
   - 来源字段：
     - `pilot_tickets_lead_continue_ally_1_v1`：`["english"]`
     - `pilot_tickets_lead_continue_ally_1_v2`：`["english"]`
     - `pilot_tickets_lead_continue_ally_1_v3`：`["english"]`
     - `pilot_tickets_lead_continue_ally_2_v1`：`["english"]`
     - `pilot_tickets_lead_continue_ally_2_v2`：`["english"]`
     - `pilot_tickets_lead_continue_ally_2_v3`：`["english"]`
     - `pilot_tickets_lead_continue_ally_3_v1`：`["english"]`
     - `pilot_tickets_lead_continue_ally_3_v2`：`["english"]`
     - `pilot_tickets_lead_continue_ally_3_v3`：`["english"]`

6. `pilot_tickets_lead_continue_enemy`

   - 组键：`pilot_tickets_lead_continue_enemy`
   - 基础名称：`pilot_tickets_lead_continue_enemy`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：`态势播报`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_tickets_lead_continue_enemy_1_v1`
     - `pilot_tickets_lead_continue_enemy_1_v2`
     - `pilot_tickets_lead_continue_enemy_1_v3`
     - `pilot_tickets_lead_continue_enemy_2_v1`
     - `pilot_tickets_lead_continue_enemy_2_v2`
     - `pilot_tickets_lead_continue_enemy_2_v3`
     - `pilot_tickets_lead_continue_enemy_3_v1`
     - `pilot_tickets_lead_continue_enemy_3_v2`
     - `pilot_tickets_lead_continue_enemy_3_v3`
   - 来源字段：
     - `pilot_tickets_lead_continue_enemy_1_v1`：`["english"]`
     - `pilot_tickets_lead_continue_enemy_1_v2`：`["english"]`
     - `pilot_tickets_lead_continue_enemy_1_v3`：`["english"]`
     - `pilot_tickets_lead_continue_enemy_2_v1`：`["english"]`
     - `pilot_tickets_lead_continue_enemy_2_v2`：`["english"]`
     - `pilot_tickets_lead_continue_enemy_2_v3`：`["english"]`
     - `pilot_tickets_lead_continue_enemy_3_v1`：`["english"]`
     - `pilot_tickets_lead_continue_enemy_3_v2`：`["english"]`
     - `pilot_tickets_lead_continue_enemy_3_v3`：`["english"]`

7. `pilot_tickets_lead_start_ally`

   - 组键：`pilot_tickets_lead_start_ally`
   - 基础名称：`pilot_tickets_lead_start_ally`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：`态势播报`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_tickets_lead_start_ally_1_v1`
     - `pilot_tickets_lead_start_ally_1_v2`
     - `pilot_tickets_lead_start_ally_1_v3`
     - `pilot_tickets_lead_start_ally_2_v1`
     - `pilot_tickets_lead_start_ally_2_v2`
     - `pilot_tickets_lead_start_ally_2_v3`
     - `pilot_tickets_lead_start_ally_3_v1`
     - `pilot_tickets_lead_start_ally_3_v2`
     - `pilot_tickets_lead_start_ally_3_v3`
   - 来源字段：
     - `pilot_tickets_lead_start_ally_1_v1`：`["english"]`
     - `pilot_tickets_lead_start_ally_1_v2`：`["english"]`
     - `pilot_tickets_lead_start_ally_1_v3`：`["english"]`
     - `pilot_tickets_lead_start_ally_2_v1`：`["english"]`
     - `pilot_tickets_lead_start_ally_2_v2`：`["english"]`
     - `pilot_tickets_lead_start_ally_2_v3`：`["english"]`
     - `pilot_tickets_lead_start_ally_3_v1`：`["english"]`
     - `pilot_tickets_lead_start_ally_3_v2`：`["english"]`
     - `pilot_tickets_lead_start_ally_3_v3`：`["english"]`

8. `pilot_tickets_lead_start_enemy`

   - 组键：`pilot_tickets_lead_start_enemy`
   - 基础名称：`pilot_tickets_lead_start_enemy`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：`态势播报`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_tickets_lead_start_enemy_1_v1`
     - `pilot_tickets_lead_start_enemy_1_v2`
     - `pilot_tickets_lead_start_enemy_1_v3`
     - `pilot_tickets_lead_start_enemy_2_v1`
     - `pilot_tickets_lead_start_enemy_2_v2`
     - `pilot_tickets_lead_start_enemy_2_v3`
     - `pilot_tickets_lead_start_enemy_3_v1`
     - `pilot_tickets_lead_start_enemy_3_v2`
     - `pilot_tickets_lead_start_enemy_3_v3`
   - 来源字段：
     - `pilot_tickets_lead_start_enemy_1_v1`：`["english"]`
     - `pilot_tickets_lead_start_enemy_1_v2`：`["english"]`
     - `pilot_tickets_lead_start_enemy_1_v3`：`["english"]`
     - `pilot_tickets_lead_start_enemy_2_v1`：`["english"]`
     - `pilot_tickets_lead_start_enemy_2_v2`：`["english"]`
     - `pilot_tickets_lead_start_enemy_2_v3`：`["english"]`
     - `pilot_tickets_lead_start_enemy_3_v1`：`["english"]`
     - `pilot_tickets_lead_start_enemy_3_v2`：`["english"]`
     - `pilot_tickets_lead_start_enemy_3_v3`：`["english"]`

9. `pilot_tickets_lead_zone_ally`

   - 组键：`pilot_tickets_lead_zone_ally`
   - 基础名称：`pilot_tickets_lead_zone_ally`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：`态势播报`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_tickets_lead_zone_ally_1_v1`
     - `pilot_tickets_lead_zone_ally_1_v2`
     - `pilot_tickets_lead_zone_ally_1_v3`
     - `pilot_tickets_lead_zone_ally_2_v1`
     - `pilot_tickets_lead_zone_ally_2_v2`
     - `pilot_tickets_lead_zone_ally_2_v3`
     - `pilot_tickets_lead_zone_ally_3_v1`
     - `pilot_tickets_lead_zone_ally_3_v2`
     - `pilot_tickets_lead_zone_ally_3_v3`
   - 来源字段：
     - `pilot_tickets_lead_zone_ally_1_v1`：`["english"]`
     - `pilot_tickets_lead_zone_ally_1_v2`：`["english"]`
     - `pilot_tickets_lead_zone_ally_1_v3`：`["english"]`
     - `pilot_tickets_lead_zone_ally_2_v1`：`["english"]`
     - `pilot_tickets_lead_zone_ally_2_v2`：`["english"]`
     - `pilot_tickets_lead_zone_ally_2_v3`：`["english"]`
     - `pilot_tickets_lead_zone_ally_3_v1`：`["english"]`
     - `pilot_tickets_lead_zone_ally_3_v2`：`["english"]`
     - `pilot_tickets_lead_zone_ally_3_v3`：`["english"]`

10. `pilot_tickets_lead_zone_enemy`

   - 组键：`pilot_tickets_lead_zone_enemy`
   - 基础名称：`pilot_tickets_lead_zone_enemy`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：`态势播报`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_tickets_lead_zone_enemy_1_v1`
     - `pilot_tickets_lead_zone_enemy_1_v2`
     - `pilot_tickets_lead_zone_enemy_1_v3`
     - `pilot_tickets_lead_zone_enemy_2_v1`
     - `pilot_tickets_lead_zone_enemy_2_v2`
     - `pilot_tickets_lead_zone_enemy_2_v3`
     - `pilot_tickets_lead_zone_enemy_3_v1`
     - `pilot_tickets_lead_zone_enemy_3_v2`
     - `pilot_tickets_lead_zone_enemy_3_v3`
   - 来源字段：
     - `pilot_tickets_lead_zone_enemy_1_v1`：`["english"]`
     - `pilot_tickets_lead_zone_enemy_1_v2`：`["english"]`
     - `pilot_tickets_lead_zone_enemy_1_v3`：`["english"]`
     - `pilot_tickets_lead_zone_enemy_2_v1`：`["english"]`
     - `pilot_tickets_lead_zone_enemy_2_v2`：`["english"]`
     - `pilot_tickets_lead_zone_enemy_2_v3`：`["english"]`
     - `pilot_tickets_lead_zone_enemy_3_v1`：`["english"]`
     - `pilot_tickets_lead_zone_enemy_3_v2`：`["english"]`
     - `pilot_tickets_lead_zone_enemy_3_v3`：`["english"]`

### 4.3 additional_01

1. `voice_message_air`

   - 组键：`voice_message_air`
   - 基础名称：`voice_message_air`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`additional_01`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_air_v1`
     - `voice_message_air_v2`
     - `voice_message_air_v3`
   - 来源字段：
     - `voice_message_air_v1`：`["additional_01"]`
     - `voice_message_air_v2`：`["additional_01"]`
     - `voice_message_air_v3`：`["additional_01"]`

2. `voice_message_air_recon`

   - 组键：`voice_message_air_recon`
   - 基础名称：`voice_message_air_recon`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`additional_01`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_air_recon_v1`
     - `voice_message_air_recon_v2`
     - `voice_message_air_recon_v3`
   - 来源字段：
     - `voice_message_air_recon_v1`：`["additional_01"]`
     - `voice_message_air_recon_v2`：`["additional_01"]`
     - `voice_message_air_recon_v3`：`["additional_01"]`

3. `voice_message_air_support`

   - 组键：`voice_message_air_support`
   - 基础名称：`voice_message_air_support`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`additional_01`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_air_support_v1`
     - `voice_message_air_support_v2`
     - `voice_message_air_support_v3`
   - 来源字段：
     - `voice_message_air_support_v1`：`["additional_01"]`
     - `voice_message_air_support_v2`：`["additional_01"]`
     - `voice_message_air_support_v3`：`["additional_01"]`

4. `voice_message_bearing`

   - 组键：`voice_message_bearing`
   - 基础名称：`voice_message_bearing`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`additional_01`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_bearing_v1`
     - `voice_message_bearing_v2`
     - `voice_message_bearing_v3`
   - 来源字段：
     - `voice_message_bearing_v1`：`["additional_01"]`
     - `voice_message_bearing_v2`：`["additional_01"]`
     - `voice_message_bearing_v3`：`["additional_01"]`

5. `voice_message_degrees`

   - 组键：`voice_message_degrees`
   - 基础名称：`voice_message_degrees`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`additional_01`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_degrees_v1`
     - `voice_message_degrees_v2`
     - `voice_message_degrees_v3`
   - 来源字段：
     - `voice_message_degrees_v1`：`["additional_01"]`
     - `voice_message_degrees_v2`：`["additional_01"]`
     - `voice_message_degrees_v3`：`["additional_01"]`

6. `voice_message_height`

   - 组键：`voice_message_height`
   - 基础名称：`voice_message_height`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`additional_01`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_height_v1`
     - `voice_message_height_v2`
     - `voice_message_height_v3`
   - 来源字段：
     - `voice_message_height_v1`：`["additional_01"]`
     - `voice_message_height_v2`：`["additional_01"]`
     - `voice_message_height_v3`：`["additional_01"]`

7. `voice_message_recon_enemy_spotted`

   - 组键：`voice_message_recon_enemy_spotted`
   - 基础名称：`voice_message_recon_enemy_spotted`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`additional_01`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_recon_enemy_spotted_v1`
     - `voice_message_recon_enemy_spotted_v2`
     - `voice_message_recon_enemy_spotted_v3`
   - 来源字段：
     - `voice_message_recon_enemy_spotted_v1`：`["additional_01"]`
     - `voice_message_recon_enemy_spotted_v2`：`["additional_01"]`
     - `voice_message_recon_enemy_spotted_v3`：`["additional_01"]`

8. `voice_message_target_for_airstrike`

   - 组键：`voice_message_target_for_airstrike`
   - 基础名称：`voice_message_target_for_airstrike`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`additional_01`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_target_for_airstrike_v1`
     - `voice_message_target_for_airstrike_v2`
     - `voice_message_target_for_airstrike_v3`
   - 来源字段：
     - `voice_message_target_for_airstrike_v1`：`["additional_01"]`
     - `voice_message_target_for_airstrike_v2`：`["additional_01"]`
     - `voice_message_target_for_airstrike_v3`：`["additional_01"]`

9. `voice_message_tech_assist`

   - 组键：`voice_message_tech_assist`
   - 基础名称：`voice_message_tech_assist`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：`additional_01`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_tech_assist_v1`
     - `voice_message_tech_assist_v2`
     - `voice_message_tech_assist_v3`
   - 来源字段：
     - `voice_message_tech_assist_v1`：`["additional_01"]`
     - `voice_message_tech_assist_v2`：`["additional_01"]`
     - `voice_message_tech_assist_v3`：`["additional_01"]`

### 4.4 信息

1. `voice_message_attack_A`

   - 组键：`voice_message_attack_A`
   - 基础名称：`voice_message_attack_A`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_attack_A_0_1`
     - `voice_message_attack_A_0_2`
     - `voice_message_attack_A_0_3`
     - `voice_message_attack_A_1_1`
     - `voice_message_attack_A_1_2`
     - `voice_message_attack_A_1_3`
     - `voice_message_attack_A_2_1`
     - `voice_message_attack_A_2_2`
     - `voice_message_attack_A_2_3`
     - `voice_message_attack_A_3_1`
     - `voice_message_attack_A_3_2`
     - `voice_message_attack_A_3_3`
   - 来源字段：
     - `voice_message_attack_A_0_1`：`["voice1"]`
     - `voice_message_attack_A_0_2`：`["voice1"]`
     - `voice_message_attack_A_0_3`：`["voice1"]`
     - `voice_message_attack_A_1_1`：`["voice1"]`
     - `voice_message_attack_A_1_2`：`["voice1"]`
     - `voice_message_attack_A_1_3`：`["voice1"]`
     - `voice_message_attack_A_2_1`：`["voice1"]`
     - `voice_message_attack_A_2_2`：`["voice1"]`
     - `voice_message_attack_A_2_3`：`["voice1"]`
     - `voice_message_attack_A_3_1`：`["voice1"]`
     - `voice_message_attack_A_3_2`：`["voice1"]`
     - `voice_message_attack_A_3_3`：`["voice1"]`

2. `voice_message_attack_B`

   - 组键：`voice_message_attack_B`
   - 基础名称：`voice_message_attack_B`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_attack_B_0_1`
     - `voice_message_attack_B_0_2`
     - `voice_message_attack_B_0_3`
     - `voice_message_attack_B_1_1`
     - `voice_message_attack_B_1_2`
     - `voice_message_attack_B_1_3`
     - `voice_message_attack_B_2_1`
     - `voice_message_attack_B_2_2`
     - `voice_message_attack_B_2_3`
     - `voice_message_attack_B_3_1`
     - `voice_message_attack_B_3_2`
     - `voice_message_attack_B_3_3`
   - 来源字段：
     - `voice_message_attack_B_0_1`：`["voice1"]`
     - `voice_message_attack_B_0_2`：`["voice1"]`
     - `voice_message_attack_B_0_3`：`["voice1"]`
     - `voice_message_attack_B_1_1`：`["voice1"]`
     - `voice_message_attack_B_1_2`：`["voice1"]`
     - `voice_message_attack_B_1_3`：`["voice1"]`
     - `voice_message_attack_B_2_1`：`["voice1"]`
     - `voice_message_attack_B_2_2`：`["voice1"]`
     - `voice_message_attack_B_2_3`：`["voice1"]`
     - `voice_message_attack_B_3_1`：`["voice1"]`
     - `voice_message_attack_B_3_2`：`["voice1"]`
     - `voice_message_attack_B_3_3`：`["voice1"]`

3. `voice_message_attack_C`

   - 组键：`voice_message_attack_C`
   - 基础名称：`voice_message_attack_C`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_attack_C_0_1`
     - `voice_message_attack_C_0_2`
     - `voice_message_attack_C_0_3`
     - `voice_message_attack_C_1_1`
     - `voice_message_attack_C_1_2`
     - `voice_message_attack_C_1_3`
     - `voice_message_attack_C_2_1`
     - `voice_message_attack_C_2_2`
     - `voice_message_attack_C_2_3`
     - `voice_message_attack_C_3_1`
     - `voice_message_attack_C_3_2`
     - `voice_message_attack_C_3_3`
   - 来源字段：
     - `voice_message_attack_C_0_1`：`["voice1"]`
     - `voice_message_attack_C_0_2`：`["voice1"]`
     - `voice_message_attack_C_0_3`：`["voice1"]`
     - `voice_message_attack_C_1_1`：`["voice1"]`
     - `voice_message_attack_C_1_2`：`["voice1"]`
     - `voice_message_attack_C_1_3`：`["voice1"]`
     - `voice_message_attack_C_2_1`：`["voice1"]`
     - `voice_message_attack_C_2_2`：`["voice1"]`
     - `voice_message_attack_C_2_3`：`["voice1"]`
     - `voice_message_attack_C_3_1`：`["voice1"]`
     - `voice_message_attack_C_3_2`：`["voice1"]`
     - `voice_message_attack_C_3_3`：`["voice1"]`

4. `voice_message_attack_D`

   - 组键：`voice_message_attack_D`
   - 基础名称：`voice_message_attack_D`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_attack_D_0_1`
     - `voice_message_attack_D_0_2`
     - `voice_message_attack_D_0_3`
     - `voice_message_attack_D_1_1`
     - `voice_message_attack_D_1_2`
     - `voice_message_attack_D_1_3`
     - `voice_message_attack_D_2_1`
     - `voice_message_attack_D_2_2`
     - `voice_message_attack_D_2_3`
     - `voice_message_attack_D_3_1`
     - `voice_message_attack_D_3_2`
     - `voice_message_attack_D_3_3`
   - 来源字段：
     - `voice_message_attack_D_0_1`：`["voice1"]`
     - `voice_message_attack_D_0_2`：`["voice1"]`
     - `voice_message_attack_D_0_3`：`["voice1"]`
     - `voice_message_attack_D_1_1`：`["voice1"]`
     - `voice_message_attack_D_1_2`：`["voice1"]`
     - `voice_message_attack_D_1_3`：`["voice1"]`
     - `voice_message_attack_D_2_1`：`["voice1"]`
     - `voice_message_attack_D_2_2`：`["voice1"]`
     - `voice_message_attack_D_2_3`：`["voice1"]`
     - `voice_message_attack_D_3_1`：`["voice1"]`
     - `voice_message_attack_D_3_2`：`["voice1"]`
     - `voice_message_attack_D_3_3`：`["voice1"]`

5. `voice_message_attack_enemy_base`

   - 组键：`voice_message_attack_enemy_base`
   - 基础名称：`voice_message_attack_enemy_base`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_attack_enemy_base_0_1`
     - `voice_message_attack_enemy_base_0_2`
     - `voice_message_attack_enemy_base_0_3`
     - `voice_message_attack_enemy_base_1_1`
     - `voice_message_attack_enemy_base_1_2`
     - `voice_message_attack_enemy_base_1_3`
     - `voice_message_attack_enemy_base_2_1`
     - `voice_message_attack_enemy_base_2_2`
     - `voice_message_attack_enemy_base_2_3`
     - `voice_message_attack_enemy_base_3_1`
     - `voice_message_attack_enemy_base_3_2`
     - `voice_message_attack_enemy_base_3_3`
   - 来源字段：
     - `voice_message_attack_enemy_base_0_1`：`["voice1"]`
     - `voice_message_attack_enemy_base_0_2`：`["voice1"]`
     - `voice_message_attack_enemy_base_0_3`：`["voice1"]`
     - `voice_message_attack_enemy_base_1_1`：`["voice1"]`
     - `voice_message_attack_enemy_base_1_2`：`["voice1"]`
     - `voice_message_attack_enemy_base_1_3`：`["voice1"]`
     - `voice_message_attack_enemy_base_2_1`：`["voice1"]`
     - `voice_message_attack_enemy_base_2_2`：`["voice1"]`
     - `voice_message_attack_enemy_base_2_3`：`["voice1"]`
     - `voice_message_attack_enemy_base_3_1`：`["voice1"]`
     - `voice_message_attack_enemy_base_3_2`：`["voice1"]`
     - `voice_message_attack_enemy_base_3_3`：`["voice1"]`

6. `voice_message_attack_enemy_troops`

   - 组键：`voice_message_attack_enemy_troops`
   - 基础名称：`voice_message_attack_enemy_troops`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_attack_enemy_troops_0_1`
     - `voice_message_attack_enemy_troops_0_2`
     - `voice_message_attack_enemy_troops_0_3`
     - `voice_message_attack_enemy_troops_1_1`
     - `voice_message_attack_enemy_troops_1_2`
     - `voice_message_attack_enemy_troops_1_3`
     - `voice_message_attack_enemy_troops_2_1`
     - `voice_message_attack_enemy_troops_2_2`
     - `voice_message_attack_enemy_troops_2_3`
     - `voice_message_attack_enemy_troops_3_1`
     - `voice_message_attack_enemy_troops_3_2`
     - `voice_message_attack_enemy_troops_3_3`
   - 来源字段：
     - `voice_message_attack_enemy_troops_0_1`：`["voice1"]`
     - `voice_message_attack_enemy_troops_0_2`：`["voice1"]`
     - `voice_message_attack_enemy_troops_0_3`：`["voice1"]`
     - `voice_message_attack_enemy_troops_1_1`：`["voice1"]`
     - `voice_message_attack_enemy_troops_1_2`：`["voice1"]`
     - `voice_message_attack_enemy_troops_1_3`：`["voice1"]`
     - `voice_message_attack_enemy_troops_2_1`：`["voice1"]`
     - `voice_message_attack_enemy_troops_2_2`：`["voice1"]`
     - `voice_message_attack_enemy_troops_2_3`：`["voice1"]`
     - `voice_message_attack_enemy_troops_3_1`：`["voice1"]`
     - `voice_message_attack_enemy_troops_3_2`：`["voice1"]`
     - `voice_message_attack_enemy_troops_3_3`：`["voice1"]`

7. `voice_message_attack_target`

   - 组键：`voice_message_attack_target`
   - 基础名称：`voice_message_attack_target`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_attack_target_0_1`
     - `voice_message_attack_target_0_2`
     - `voice_message_attack_target_0_3`
     - `voice_message_attack_target_1_1`
     - `voice_message_attack_target_1_2`
     - `voice_message_attack_target_1_3`
     - `voice_message_attack_target_2_1`
     - `voice_message_attack_target_2_2`
     - `voice_message_attack_target_2_3`
     - `voice_message_attack_target_3_1`
     - `voice_message_attack_target_3_2`
     - `voice_message_attack_target_3_3`
   - 来源字段：
     - `voice_message_attack_target_0_1`：`["voice1"]`
     - `voice_message_attack_target_0_2`：`["voice1"]`
     - `voice_message_attack_target_0_3`：`["voice1"]`
     - `voice_message_attack_target_1_1`：`["voice1"]`
     - `voice_message_attack_target_1_2`：`["voice1"]`
     - `voice_message_attack_target_1_3`：`["voice1"]`
     - `voice_message_attack_target_2_1`：`["voice1"]`
     - `voice_message_attack_target_2_2`：`["voice1"]`
     - `voice_message_attack_target_2_3`：`["voice1"]`
     - `voice_message_attack_target_3_1`：`["voice1"]`
     - `voice_message_attack_target_3_2`：`["voice1"]`
     - `voice_message_attack_target_3_3`：`["voice1"]`

8. `voice_message_attacking_target`

   - 组键：`voice_message_attacking_target`
   - 基础名称：`voice_message_attacking_target`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_attacking_target_0_1`
     - `voice_message_attacking_target_0_2`
     - `voice_message_attacking_target_0_3`
     - `voice_message_attacking_target_1_1`
     - `voice_message_attacking_target_1_2`
     - `voice_message_attacking_target_1_3`
     - `voice_message_attacking_target_2_1`
     - `voice_message_attacking_target_2_2`
     - `voice_message_attacking_target_2_3`
     - `voice_message_attacking_target_3_1`
     - `voice_message_attacking_target_3_2`
     - `voice_message_attacking_target_3_3`
   - 来源字段：
     - `voice_message_attacking_target_0_1`：`["voice1"]`
     - `voice_message_attacking_target_0_2`：`["voice1"]`
     - `voice_message_attacking_target_0_3`：`["voice1"]`
     - `voice_message_attacking_target_1_1`：`["voice1"]`
     - `voice_message_attacking_target_1_2`：`["voice1"]`
     - `voice_message_attacking_target_1_3`：`["voice1"]`
     - `voice_message_attacking_target_2_1`：`["voice1"]`
     - `voice_message_attacking_target_2_2`：`["voice1"]`
     - `voice_message_attacking_target_2_3`：`["voice1"]`
     - `voice_message_attacking_target_3_1`：`["voice1"]`
     - `voice_message_attacking_target_3_2`：`["voice1"]`
     - `voice_message_attacking_target_3_3`：`["voice1"]`

9. `voice_message_attention_to_point`

   - 组键：`voice_message_attention_to_point`
   - 基础名称：`voice_message_attention_to_point`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_attention_to_point_0_1`
     - `voice_message_attention_to_point_0_2`
     - `voice_message_attention_to_point_0_3`
     - `voice_message_attention_to_point_1_1`
     - `voice_message_attention_to_point_1_2`
     - `voice_message_attention_to_point_1_3`
     - `voice_message_attention_to_point_2_1`
     - `voice_message_attention_to_point_2_2`
     - `voice_message_attention_to_point_2_3`
     - `voice_message_attention_to_point_3_1`
     - `voice_message_attention_to_point_3_2`
     - `voice_message_attention_to_point_3_3`
   - 来源字段：
     - `voice_message_attention_to_point_0_1`：`["voice1"]`
     - `voice_message_attention_to_point_0_2`：`["voice1"]`
     - `voice_message_attention_to_point_0_3`：`["voice1"]`
     - `voice_message_attention_to_point_1_1`：`["voice1"]`
     - `voice_message_attention_to_point_1_2`：`["voice1"]`
     - `voice_message_attention_to_point_1_3`：`["voice1"]`
     - `voice_message_attention_to_point_2_1`：`["voice1"]`
     - `voice_message_attention_to_point_2_2`：`["voice1"]`
     - `voice_message_attention_to_point_2_3`：`["voice1"]`
     - `voice_message_attention_to_point_3_1`：`["voice1"]`
     - `voice_message_attention_to_point_3_2`：`["voice1"]`
     - `voice_message_attention_to_point_3_3`：`["voice1"]`

10. `voice_message_check_your_six`

   - 组键：`voice_message_check_your_six`
   - 基础名称：`voice_message_check_your_six`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_check_your_six_0_1`
     - `voice_message_check_your_six_0_2`
     - `voice_message_check_your_six_0_3`
     - `voice_message_check_your_six_1_1`
     - `voice_message_check_your_six_1_2`
     - `voice_message_check_your_six_1_3`
     - `voice_message_check_your_six_2_1`
     - `voice_message_check_your_six_2_2`
     - `voice_message_check_your_six_2_3`
     - `voice_message_check_your_six_3_1`
     - `voice_message_check_your_six_3_2`
     - `voice_message_check_your_six_3_3`
   - 来源字段：
     - `voice_message_check_your_six_0_1`：`["voice1"]`
     - `voice_message_check_your_six_0_2`：`["voice1"]`
     - `voice_message_check_your_six_0_3`：`["voice1"]`
     - `voice_message_check_your_six_1_1`：`["voice1"]`
     - `voice_message_check_your_six_1_2`：`["voice1"]`
     - `voice_message_check_your_six_1_3`：`["voice1"]`
     - `voice_message_check_your_six_2_1`：`["voice1"]`
     - `voice_message_check_your_six_2_2`：`["voice1"]`
     - `voice_message_check_your_six_2_3`：`["voice1"]`
     - `voice_message_check_your_six_3_1`：`["voice1"]`
     - `voice_message_check_your_six_3_2`：`["voice1"]`
     - `voice_message_check_your_six_3_3`：`["voice1"]`

11. `voice_message_cover_base`

   - 组键：`voice_message_cover_base`
   - 基础名称：`voice_message_cover_base`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_cover_base_0_1`
     - `voice_message_cover_base_0_2`
     - `voice_message_cover_base_0_3`
     - `voice_message_cover_base_1_1`
     - `voice_message_cover_base_1_2`
     - `voice_message_cover_base_1_3`
     - `voice_message_cover_base_2_1`
     - `voice_message_cover_base_2_2`
     - `voice_message_cover_base_2_3`
     - `voice_message_cover_base_3_1`
     - `voice_message_cover_base_3_2`
     - `voice_message_cover_base_3_3`
   - 来源字段：
     - `voice_message_cover_base_0_1`：`["voice1"]`
     - `voice_message_cover_base_0_2`：`["voice1"]`
     - `voice_message_cover_base_0_3`：`["voice1"]`
     - `voice_message_cover_base_1_1`：`["voice1"]`
     - `voice_message_cover_base_1_2`：`["voice1"]`
     - `voice_message_cover_base_1_3`：`["voice1"]`
     - `voice_message_cover_base_2_1`：`["voice1"]`
     - `voice_message_cover_base_2_2`：`["voice1"]`
     - `voice_message_cover_base_2_3`：`["voice1"]`
     - `voice_message_cover_base_3_1`：`["voice1"]`
     - `voice_message_cover_base_3_2`：`["voice1"]`
     - `voice_message_cover_base_3_3`：`["voice1"]`

12. `voice_message_cover_me`

   - 组键：`voice_message_cover_me`
   - 基础名称：`voice_message_cover_me`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_cover_me_0_1`
     - `voice_message_cover_me_0_2`
     - `voice_message_cover_me_0_3`
     - `voice_message_cover_me_1_1`
     - `voice_message_cover_me_1_2`
     - `voice_message_cover_me_1_3`
     - `voice_message_cover_me_2_1`
     - `voice_message_cover_me_2_2`
     - `voice_message_cover_me_2_3`
     - `voice_message_cover_me_3_1`
     - `voice_message_cover_me_3_2`
     - `voice_message_cover_me_3_3`
   - 来源字段：
     - `voice_message_cover_me_0_1`：`["voice1"]`
     - `voice_message_cover_me_0_2`：`["voice1"]`
     - `voice_message_cover_me_0_3`：`["voice1"]`
     - `voice_message_cover_me_1_1`：`["voice1"]`
     - `voice_message_cover_me_1_2`：`["voice1"]`
     - `voice_message_cover_me_1_3`：`["voice1"]`
     - `voice_message_cover_me_2_1`：`["voice1"]`
     - `voice_message_cover_me_2_2`：`["voice1"]`
     - `voice_message_cover_me_2_3`：`["voice1"]`
     - `voice_message_cover_me_3_1`：`["voice1"]`
     - `voice_message_cover_me_3_2`：`["voice1"]`
     - `voice_message_cover_me_3_3`：`["voice1"]`

13. `voice_message_defend_A`

   - 组键：`voice_message_defend_A`
   - 基础名称：`voice_message_defend_A`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_defend_A_0_1`
     - `voice_message_defend_A_0_2`
     - `voice_message_defend_A_0_3`
     - `voice_message_defend_A_1_1`
     - `voice_message_defend_A_1_2`
     - `voice_message_defend_A_1_3`
     - `voice_message_defend_A_2_1`
     - `voice_message_defend_A_2_2`
     - `voice_message_defend_A_2_3`
     - `voice_message_defend_A_3_1`
     - `voice_message_defend_A_3_2`
     - `voice_message_defend_A_3_3`
   - 来源字段：
     - `voice_message_defend_A_0_1`：`["voice1"]`
     - `voice_message_defend_A_0_2`：`["voice1"]`
     - `voice_message_defend_A_0_3`：`["voice1"]`
     - `voice_message_defend_A_1_1`：`["voice1"]`
     - `voice_message_defend_A_1_2`：`["voice1"]`
     - `voice_message_defend_A_1_3`：`["voice1"]`
     - `voice_message_defend_A_2_1`：`["voice1"]`
     - `voice_message_defend_A_2_2`：`["voice1"]`
     - `voice_message_defend_A_2_3`：`["voice1"]`
     - `voice_message_defend_A_3_1`：`["voice1"]`
     - `voice_message_defend_A_3_2`：`["voice1"]`
     - `voice_message_defend_A_3_3`：`["voice1"]`

14. `voice_message_defend_B`

   - 组键：`voice_message_defend_B`
   - 基础名称：`voice_message_defend_B`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_defend_B_0_1`
     - `voice_message_defend_B_0_2`
     - `voice_message_defend_B_0_3`
     - `voice_message_defend_B_1_1`
     - `voice_message_defend_B_1_2`
     - `voice_message_defend_B_1_3`
     - `voice_message_defend_B_2_1`
     - `voice_message_defend_B_2_2`
     - `voice_message_defend_B_2_3`
     - `voice_message_defend_B_3_1`
     - `voice_message_defend_B_3_2`
     - `voice_message_defend_B_3_3`
   - 来源字段：
     - `voice_message_defend_B_0_1`：`["voice1"]`
     - `voice_message_defend_B_0_2`：`["voice1"]`
     - `voice_message_defend_B_0_3`：`["voice1"]`
     - `voice_message_defend_B_1_1`：`["voice1"]`
     - `voice_message_defend_B_1_2`：`["voice1"]`
     - `voice_message_defend_B_1_3`：`["voice1"]`
     - `voice_message_defend_B_2_1`：`["voice1"]`
     - `voice_message_defend_B_2_2`：`["voice1"]`
     - `voice_message_defend_B_2_3`：`["voice1"]`
     - `voice_message_defend_B_3_1`：`["voice1"]`
     - `voice_message_defend_B_3_2`：`["voice1"]`
     - `voice_message_defend_B_3_3`：`["voice1"]`

15. `voice_message_defend_C`

   - 组键：`voice_message_defend_C`
   - 基础名称：`voice_message_defend_C`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_defend_C_0_1`
     - `voice_message_defend_C_0_2`
     - `voice_message_defend_C_0_3`
     - `voice_message_defend_C_1_1`
     - `voice_message_defend_C_1_2`
     - `voice_message_defend_C_1_3`
     - `voice_message_defend_C_2_1`
     - `voice_message_defend_C_2_2`
     - `voice_message_defend_C_2_3`
     - `voice_message_defend_C_3_1`
     - `voice_message_defend_C_3_2`
     - `voice_message_defend_C_3_3`
   - 来源字段：
     - `voice_message_defend_C_0_1`：`["voice1"]`
     - `voice_message_defend_C_0_2`：`["voice1"]`
     - `voice_message_defend_C_0_3`：`["voice1"]`
     - `voice_message_defend_C_1_1`：`["voice1"]`
     - `voice_message_defend_C_1_2`：`["voice1"]`
     - `voice_message_defend_C_1_3`：`["voice1"]`
     - `voice_message_defend_C_2_1`：`["voice1"]`
     - `voice_message_defend_C_2_2`：`["voice1"]`
     - `voice_message_defend_C_2_3`：`["voice1"]`
     - `voice_message_defend_C_3_1`：`["voice1"]`
     - `voice_message_defend_C_3_2`：`["voice1"]`
     - `voice_message_defend_C_3_3`：`["voice1"]`

16. `voice_message_defend_D`

   - 组键：`voice_message_defend_D`
   - 基础名称：`voice_message_defend_D`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_defend_D_0_1`
     - `voice_message_defend_D_0_2`
     - `voice_message_defend_D_0_3`
     - `voice_message_defend_D_1_1`
     - `voice_message_defend_D_1_2`
     - `voice_message_defend_D_1_3`
     - `voice_message_defend_D_2_1`
     - `voice_message_defend_D_2_2`
     - `voice_message_defend_D_2_3`
     - `voice_message_defend_D_3_1`
     - `voice_message_defend_D_3_2`
     - `voice_message_defend_D_3_3`
   - 来源字段：
     - `voice_message_defend_D_0_1`：`["voice1"]`
     - `voice_message_defend_D_0_2`：`["voice1"]`
     - `voice_message_defend_D_0_3`：`["voice1"]`
     - `voice_message_defend_D_1_1`：`["voice1"]`
     - `voice_message_defend_D_1_2`：`["voice1"]`
     - `voice_message_defend_D_1_3`：`["voice1"]`
     - `voice_message_defend_D_2_1`：`["voice1"]`
     - `voice_message_defend_D_2_2`：`["voice1"]`
     - `voice_message_defend_D_2_3`：`["voice1"]`
     - `voice_message_defend_D_3_1`：`["voice1"]`
     - `voice_message_defend_D_3_2`：`["voice1"]`
     - `voice_message_defend_D_3_3`：`["voice1"]`

17. `voice_message_follow_me`

   - 组键：`voice_message_follow_me`
   - 基础名称：`voice_message_follow_me`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_follow_me_0_1`
     - `voice_message_follow_me_0_2`
     - `voice_message_follow_me_0_3`
     - `voice_message_follow_me_1_1`
     - `voice_message_follow_me_1_2`
     - `voice_message_follow_me_1_3`
     - `voice_message_follow_me_2_1`
     - `voice_message_follow_me_2_2`
     - `voice_message_follow_me_2_3`
     - `voice_message_follow_me_3_1`
     - `voice_message_follow_me_3_2`
     - `voice_message_follow_me_3_3`
   - 来源字段：
     - `voice_message_follow_me_0_1`：`["voice1"]`
     - `voice_message_follow_me_0_2`：`["voice1"]`
     - `voice_message_follow_me_0_3`：`["voice1"]`
     - `voice_message_follow_me_1_1`：`["voice1"]`
     - `voice_message_follow_me_1_2`：`["voice1"]`
     - `voice_message_follow_me_1_3`：`["voice1"]`
     - `voice_message_follow_me_2_1`：`["voice1"]`
     - `voice_message_follow_me_2_2`：`["voice1"]`
     - `voice_message_follow_me_2_3`：`["voice1"]`
     - `voice_message_follow_me_3_1`：`["voice1"]`
     - `voice_message_follow_me_3_2`：`["voice1"]`
     - `voice_message_follow_me_3_3`：`["voice1"]`

18. `voice_message_landing`

   - 组键：`voice_message_landing`
   - 基础名称：`voice_message_landing`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_landing_0_1`
     - `voice_message_landing_0_2`
     - `voice_message_landing_0_3`
     - `voice_message_landing_1_1`
     - `voice_message_landing_1_2`
     - `voice_message_landing_1_3`
     - `voice_message_landing_2_1`
     - `voice_message_landing_2_2`
     - `voice_message_landing_2_3`
     - `voice_message_landing_3_1`
     - `voice_message_landing_3_2`
     - `voice_message_landing_3_3`
   - 来源字段：
     - `voice_message_landing_0_1`：`["voice1"]`
     - `voice_message_landing_0_2`：`["voice1"]`
     - `voice_message_landing_0_3`：`["voice1"]`
     - `voice_message_landing_1_1`：`["voice1"]`
     - `voice_message_landing_1_2`：`["voice1"]`
     - `voice_message_landing_1_3`：`["voice1"]`
     - `voice_message_landing_2_1`：`["voice1"]`
     - `voice_message_landing_2_2`：`["voice1"]`
     - `voice_message_landing_2_3`：`["voice1"]`
     - `voice_message_landing_3_1`：`["voice1"]`
     - `voice_message_landing_3_2`：`["voice1"]`
     - `voice_message_landing_3_3`：`["voice1"]`

19. `voice_message_no`

   - 组键：`voice_message_no`
   - 基础名称：`voice_message_no`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_no_0_1`
     - `voice_message_no_0_2`
     - `voice_message_no_0_3`
     - `voice_message_no_1_1`
     - `voice_message_no_1_2`
     - `voice_message_no_1_3`
     - `voice_message_no_2_1`
     - `voice_message_no_2_2`
     - `voice_message_no_2_3`
     - `voice_message_no_3_1`
     - `voice_message_no_3_2`
     - `voice_message_no_3_3`
   - 来源字段：
     - `voice_message_no_0_1`：`["voice1"]`
     - `voice_message_no_0_2`：`["voice1"]`
     - `voice_message_no_0_3`：`["voice1"]`
     - `voice_message_no_1_1`：`["voice1"]`
     - `voice_message_no_1_2`：`["voice1"]`
     - `voice_message_no_1_3`：`["voice1"]`
     - `voice_message_no_2_1`：`["voice1"]`
     - `voice_message_no_2_2`：`["voice1"]`
     - `voice_message_no_2_3`：`["voice1"]`
     - `voice_message_no_3_1`：`["voice1"]`
     - `voice_message_no_3_2`：`["voice1"]`
     - `voice_message_no_3_3`：`["voice1"]`

20. `voice_message_reloading`

   - 组键：`voice_message_reloading`
   - 基础名称：`voice_message_reloading`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_reloading_0_1`
     - `voice_message_reloading_0_2`
     - `voice_message_reloading_0_3`
     - `voice_message_reloading_1_1`
     - `voice_message_reloading_1_2`
     - `voice_message_reloading_1_3`
     - `voice_message_reloading_2_1`
     - `voice_message_reloading_2_2`
     - `voice_message_reloading_2_3`
     - `voice_message_reloading_3_1`
     - `voice_message_reloading_3_2`
     - `voice_message_reloading_3_3`
   - 来源字段：
     - `voice_message_reloading_0_1`：`["voice1"]`
     - `voice_message_reloading_0_2`：`["voice1"]`
     - `voice_message_reloading_0_3`：`["voice1"]`
     - `voice_message_reloading_1_1`：`["voice1"]`
     - `voice_message_reloading_1_2`：`["voice1"]`
     - `voice_message_reloading_1_3`：`["voice1"]`
     - `voice_message_reloading_2_1`：`["voice1"]`
     - `voice_message_reloading_2_2`：`["voice1"]`
     - `voice_message_reloading_2_3`：`["voice1"]`
     - `voice_message_reloading_3_1`：`["voice1"]`
     - `voice_message_reloading_3_2`：`["voice1"]`
     - `voice_message_reloading_3_3`：`["voice1"]`

21. `voice_message_repairing`

   - 组键：`voice_message_repairing`
   - 基础名称：`voice_message_repairing`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_repairing_0_1`
     - `voice_message_repairing_0_2`
     - `voice_message_repairing_0_3`
     - `voice_message_repairing_1_1`
     - `voice_message_repairing_1_2`
     - `voice_message_repairing_1_3`
     - `voice_message_repairing_2_1`
     - `voice_message_repairing_2_2`
     - `voice_message_repairing_2_3`
     - `voice_message_repairing_3_1`
     - `voice_message_repairing_3_2`
     - `voice_message_repairing_3_3`
   - 来源字段：
     - `voice_message_repairing_0_1`：`["voice1"]`
     - `voice_message_repairing_0_2`：`["voice1"]`
     - `voice_message_repairing_0_3`：`["voice1"]`
     - `voice_message_repairing_1_1`：`["voice1"]`
     - `voice_message_repairing_1_2`：`["voice1"]`
     - `voice_message_repairing_1_3`：`["voice1"]`
     - `voice_message_repairing_2_1`：`["voice1"]`
     - `voice_message_repairing_2_2`：`["voice1"]`
     - `voice_message_repairing_2_3`：`["voice1"]`
     - `voice_message_repairing_3_1`：`["voice1"]`
     - `voice_message_repairing_3_2`：`["voice1"]`
     - `voice_message_repairing_3_3`：`["voice1"]`

22. `voice_message_return_to_base`

   - 组键：`voice_message_return_to_base`
   - 基础名称：`voice_message_return_to_base`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_return_to_base_0_1`
     - `voice_message_return_to_base_0_2`
     - `voice_message_return_to_base_0_3`
     - `voice_message_return_to_base_1_1`
     - `voice_message_return_to_base_1_2`
     - `voice_message_return_to_base_1_3`
     - `voice_message_return_to_base_2_1`
     - `voice_message_return_to_base_2_2`
     - `voice_message_return_to_base_2_3`
     - `voice_message_return_to_base_3_1`
     - `voice_message_return_to_base_3_2`
     - `voice_message_return_to_base_3_3`
   - 来源字段：
     - `voice_message_return_to_base_0_1`：`["voice1"]`
     - `voice_message_return_to_base_0_2`：`["voice1"]`
     - `voice_message_return_to_base_0_3`：`["voice1"]`
     - `voice_message_return_to_base_1_1`：`["voice1"]`
     - `voice_message_return_to_base_1_2`：`["voice1"]`
     - `voice_message_return_to_base_1_3`：`["voice1"]`
     - `voice_message_return_to_base_2_1`：`["voice1"]`
     - `voice_message_return_to_base_2_2`：`["voice1"]`
     - `voice_message_return_to_base_2_3`：`["voice1"]`
     - `voice_message_return_to_base_3_1`：`["voice1"]`
     - `voice_message_return_to_base_3_2`：`["voice1"]`
     - `voice_message_return_to_base_3_3`：`["voice1"]`

23. `voice_message_sorry`

   - 组键：`voice_message_sorry`
   - 基础名称：`voice_message_sorry`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_sorry_0_1`
     - `voice_message_sorry_0_2`
     - `voice_message_sorry_0_3`
     - `voice_message_sorry_1_1`
     - `voice_message_sorry_1_2`
     - `voice_message_sorry_1_3`
     - `voice_message_sorry_2_1`
     - `voice_message_sorry_2_2`
     - `voice_message_sorry_2_3`
     - `voice_message_sorry_3_1`
     - `voice_message_sorry_3_2`
     - `voice_message_sorry_3_3`
   - 来源字段：
     - `voice_message_sorry_0_1`：`["voice1"]`
     - `voice_message_sorry_0_2`：`["voice1"]`
     - `voice_message_sorry_0_3`：`["voice1"]`
     - `voice_message_sorry_1_1`：`["voice1"]`
     - `voice_message_sorry_1_2`：`["voice1"]`
     - `voice_message_sorry_1_3`：`["voice1"]`
     - `voice_message_sorry_2_1`：`["voice1"]`
     - `voice_message_sorry_2_2`：`["voice1"]`
     - `voice_message_sorry_2_3`：`["voice1"]`
     - `voice_message_sorry_3_1`：`["voice1"]`
     - `voice_message_sorry_3_2`：`["voice1"]`
     - `voice_message_sorry_3_3`：`["voice1"]`

24. `voice_message_thank_you`

   - 组键：`voice_message_thank_you`
   - 基础名称：`voice_message_thank_you`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_thank_you_0_1`
     - `voice_message_thank_you_0_2`
     - `voice_message_thank_you_0_3`
     - `voice_message_thank_you_1_1`
     - `voice_message_thank_you_1_2`
     - `voice_message_thank_you_1_3`
     - `voice_message_thank_you_2_1`
     - `voice_message_thank_you_2_2`
     - `voice_message_thank_you_2_3`
     - `voice_message_thank_you_3_1`
     - `voice_message_thank_you_3_2`
     - `voice_message_thank_you_3_3`
   - 来源字段：
     - `voice_message_thank_you_0_1`：`["voice1"]`
     - `voice_message_thank_you_0_2`：`["voice1"]`
     - `voice_message_thank_you_0_3`：`["voice1"]`
     - `voice_message_thank_you_1_1`：`["voice1"]`
     - `voice_message_thank_you_1_2`：`["voice1"]`
     - `voice_message_thank_you_1_3`：`["voice1"]`
     - `voice_message_thank_you_2_1`：`["voice1"]`
     - `voice_message_thank_you_2_2`：`["voice1"]`
     - `voice_message_thank_you_2_3`：`["voice1"]`
     - `voice_message_thank_you_3_1`：`["voice1"]`
     - `voice_message_thank_you_3_2`：`["voice1"]`
     - `voice_message_thank_you_3_3`：`["voice1"]`

25. `voice_message_well_done`

   - 组键：`voice_message_well_done`
   - 基础名称：`voice_message_well_done`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_well_done_0_1`
     - `voice_message_well_done_0_2`
     - `voice_message_well_done_0_3`
     - `voice_message_well_done_1_1`
     - `voice_message_well_done_1_2`
     - `voice_message_well_done_1_3`
     - `voice_message_well_done_2_1`
     - `voice_message_well_done_2_2`
     - `voice_message_well_done_2_3`
     - `voice_message_well_done_3_1`
     - `voice_message_well_done_3_2`
     - `voice_message_well_done_3_3`
   - 来源字段：
     - `voice_message_well_done_0_1`：`["voice1"]`
     - `voice_message_well_done_0_2`：`["voice1"]`
     - `voice_message_well_done_0_3`：`["voice1"]`
     - `voice_message_well_done_1_1`：`["voice1"]`
     - `voice_message_well_done_1_2`：`["voice1"]`
     - `voice_message_well_done_1_3`：`["voice1"]`
     - `voice_message_well_done_2_1`：`["voice1"]`
     - `voice_message_well_done_2_2`：`["voice1"]`
     - `voice_message_well_done_2_3`：`["voice1"]`
     - `voice_message_well_done_3_1`：`["voice1"]`
     - `voice_message_well_done_3_2`：`["voice1"]`
     - `voice_message_well_done_3_3`：`["voice1"]`

26. `voice_message_yes`

   - 组键：`voice_message_yes`
   - 基础名称：`voice_message_yes`
   - 命名类型：`matrix_suffix`
   - 成员数量：12
   - `module`：`radio`
   - `category`：`信息`
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `voice_message_yes_0_1`
     - `voice_message_yes_0_2`
     - `voice_message_yes_0_3`
     - `voice_message_yes_1_1`
     - `voice_message_yes_1_2`
     - `voice_message_yes_1_3`
     - `voice_message_yes_2_1`
     - `voice_message_yes_2_2`
     - `voice_message_yes_2_3`
     - `voice_message_yes_3_1`
     - `voice_message_yes_3_2`
     - `voice_message_yes_3_3`
   - 来源字段：
     - `voice_message_yes_0_1`：`["voice1"]`
     - `voice_message_yes_0_2`：`["voice1"]`
     - `voice_message_yes_0_3`：`["voice1"]`
     - `voice_message_yes_1_1`：`["voice1"]`
     - `voice_message_yes_1_2`：`["voice1"]`
     - `voice_message_yes_1_3`：`["voice1"]`
     - `voice_message_yes_2_1`：`["voice1"]`
     - `voice_message_yes_2_2`：`["voice1"]`
     - `voice_message_yes_2_3`：`["voice1"]`
     - `voice_message_yes_3_1`：`["voice1"]`
     - `voice_message_yes_3_2`：`["voice1"]`
     - `voice_message_yes_3_3`：`["voice1"]`

### 4.5 未分类项目组

> 以下组缺少 `category` 字段，但完整名称、类型与来源审计信息均存在。

1. `pilot_base_destroyed_ally`

   - 组键：`pilot_base_destroyed_ally`
   - 基础名称：`pilot_base_destroyed_ally`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_base_destroyed_ally_v1`
     - `pilot_base_destroyed_ally_v2`
     - `pilot_base_destroyed_ally_v3`
   - 来源字段：
     - `pilot_base_destroyed_ally_v1`：`["english"]`
     - `pilot_base_destroyed_ally_v2`：`["english"]`
     - `pilot_base_destroyed_ally_v3`：`["english"]`

2. `pilot_base_destroyed_enemy`

   - 组键：`pilot_base_destroyed_enemy`
   - 基础名称：`pilot_base_destroyed_enemy`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_base_destroyed_enemy_v1`
     - `pilot_base_destroyed_enemy_v2`
     - `pilot_base_destroyed_enemy_v3`
   - 来源字段：
     - `pilot_base_destroyed_enemy_v1`：`["english"]`
     - `pilot_base_destroyed_enemy_v2`：`["english"]`
     - `pilot_base_destroyed_enemy_v3`：`["english"]`

3. `pilot_base_underattack`

   - 组键：`pilot_base_underattack`
   - 基础名称：`pilot_base_underattack`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_base_underattack_1_v1`
     - `pilot_base_underattack_1_v2`
     - `pilot_base_underattack_1_v3`
     - `pilot_base_underattack_2_v1`
     - `pilot_base_underattack_2_v2`
     - `pilot_base_underattack_2_v3`
     - `pilot_base_underattack_3_v1`
     - `pilot_base_underattack_3_v2`
     - `pilot_base_underattack_3_v3`
   - 来源字段：
     - `pilot_base_underattack_1_v1`：`["english"]`
     - `pilot_base_underattack_1_v2`：`["english"]`
     - `pilot_base_underattack_1_v3`：`["english"]`
     - `pilot_base_underattack_2_v1`：`["english"]`
     - `pilot_base_underattack_2_v2`：`["english"]`
     - `pilot_base_underattack_2_v3`：`["english"]`
     - `pilot_base_underattack_3_v1`：`["english"]`
     - `pilot_base_underattack_3_v2`：`["english"]`
     - `pilot_base_underattack_3_v3`：`["english"]`

4. `pilot_capture_ground_ally`

   - 组键：`pilot_capture_ground_ally`
   - 基础名称：`pilot_capture_ground_ally`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_capture_ground_ally1_v1`
     - `pilot_capture_ground_ally1_v2`
     - `pilot_capture_ground_ally1_v3`
     - `pilot_capture_ground_ally2_v1`
     - `pilot_capture_ground_ally2_v2`
     - `pilot_capture_ground_ally2_v3`
     - `pilot_capture_ground_ally3_v1`
     - `pilot_capture_ground_ally3_v2`
     - `pilot_capture_ground_ally3_v3`
   - 来源字段：
     - `pilot_capture_ground_ally1_v1`：`["english"]`
     - `pilot_capture_ground_ally1_v2`：`["english"]`
     - `pilot_capture_ground_ally1_v3`：`["english"]`
     - `pilot_capture_ground_ally2_v1`：`["english"]`
     - `pilot_capture_ground_ally2_v2`：`["english"]`
     - `pilot_capture_ground_ally2_v3`：`["english"]`
     - `pilot_capture_ground_ally3_v1`：`["english"]`
     - `pilot_capture_ground_ally3_v2`：`["english"]`
     - `pilot_capture_ground_ally3_v3`：`["english"]`

5. `pilot_capture_ground_enemy`

   - 组键：`pilot_capture_ground_enemy`
   - 基础名称：`pilot_capture_ground_enemy`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_capture_ground_enemy1_v1`
     - `pilot_capture_ground_enemy1_v2`
     - `pilot_capture_ground_enemy1_v3`
     - `pilot_capture_ground_enemy2_v1`
     - `pilot_capture_ground_enemy2_v2`
     - `pilot_capture_ground_enemy2_v3`
     - `pilot_capture_ground_enemy3_v1`
     - `pilot_capture_ground_enemy3_v2`
     - `pilot_capture_ground_enemy3_v3`
   - 来源字段：
     - `pilot_capture_ground_enemy1_v1`：`["english"]`
     - `pilot_capture_ground_enemy1_v2`：`["english"]`
     - `pilot_capture_ground_enemy1_v3`：`["english"]`
     - `pilot_capture_ground_enemy2_v1`：`["english"]`
     - `pilot_capture_ground_enemy2_v2`：`["english"]`
     - `pilot_capture_ground_enemy2_v3`：`["english"]`
     - `pilot_capture_ground_enemy3_v1`：`["english"]`
     - `pilot_capture_ground_enemy3_v2`：`["english"]`
     - `pilot_capture_ground_enemy3_v3`：`["english"]`

6. `pilot_mission_complete`

   - 组键：`pilot_mission_complete`
   - 基础名称：`pilot_mission_complete`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_mission_complete_1_v1`
     - `pilot_mission_complete_1_v2`
     - `pilot_mission_complete_1_v3`
     - `pilot_mission_complete_2_v1`
     - `pilot_mission_complete_2_v2`
     - `pilot_mission_complete_2_v3`
     - `pilot_mission_complete_3_v1`
     - `pilot_mission_complete_3_v2`
     - `pilot_mission_complete_3_v3`
   - 来源字段：
     - `pilot_mission_complete_1_v1`：`["english"]`
     - `pilot_mission_complete_1_v2`：`["english"]`
     - `pilot_mission_complete_1_v3`：`["english"]`
     - `pilot_mission_complete_2_v1`：`["english"]`
     - `pilot_mission_complete_2_v2`：`["english"]`
     - `pilot_mission_complete_2_v3`：`["english"]`
     - `pilot_mission_complete_3_v1`：`["english"]`
     - `pilot_mission_complete_3_v2`：`["english"]`
     - `pilot_mission_complete_3_v3`：`["english"]`

7. `pilot_mission_fail`

   - 组键：`pilot_mission_fail`
   - 基础名称：`pilot_mission_fail`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_mission_fail_1_v1`
     - `pilot_mission_fail_1_v2`
     - `pilot_mission_fail_1_v3`
     - `pilot_mission_fail_2_v1`
     - `pilot_mission_fail_2_v2`
     - `pilot_mission_fail_2_v3`
     - `pilot_mission_fail_3_v1`
     - `pilot_mission_fail_3_v2`
     - `pilot_mission_fail_3_v3`
   - 来源字段：
     - `pilot_mission_fail_1_v1`：`["english"]`
     - `pilot_mission_fail_1_v2`：`["english"]`
     - `pilot_mission_fail_1_v3`：`["english"]`
     - `pilot_mission_fail_2_v1`：`["english"]`
     - `pilot_mission_fail_2_v2`：`["english"]`
     - `pilot_mission_fail_2_v3`：`["english"]`
     - `pilot_mission_fail_3_v1`：`["english"]`
     - `pilot_mission_fail_3_v2`：`["english"]`
     - `pilot_mission_fail_3_v3`：`["english"]`

8. `pilot_mission_start_add`

   - 组键：`pilot_mission_start_add`
   - 基础名称：`pilot_mission_start_add`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_mission_start_add1_v1`
     - `pilot_mission_start_add1_v2`
     - `pilot_mission_start_add1_v3`
     - `pilot_mission_start_add2_v1`
     - `pilot_mission_start_add2_v2`
     - `pilot_mission_start_add2_v3`
     - `pilot_mission_start_add3_v1`
     - `pilot_mission_start_add3_v2`
     - `pilot_mission_start_add3_v3`
   - 来源字段：
     - `pilot_mission_start_add1_v1`：`["english"]`
     - `pilot_mission_start_add1_v2`：`["english"]`
     - `pilot_mission_start_add1_v3`：`["english"]`
     - `pilot_mission_start_add2_v1`：`["english"]`
     - `pilot_mission_start_add2_v2`：`["english"]`
     - `pilot_mission_start_add2_v3`：`["english"]`
     - `pilot_mission_start_add3_v1`：`["english"]`
     - `pilot_mission_start_add3_v2`：`["english"]`
     - `pilot_mission_start_add3_v3`：`["english"]`

9. `pilot_point_underattack`

   - 组键：`pilot_point_underattack`
   - 基础名称：`pilot_point_underattack`
   - 命名类型：`v_matrix_suffix`
   - 成员数量：9
   - `module`：`radio`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_point_underattack_1_v1`
     - `pilot_point_underattack_1_v2`
     - `pilot_point_underattack_1_v3`
     - `pilot_point_underattack_2_v1`
     - `pilot_point_underattack_2_v2`
     - `pilot_point_underattack_2_v3`
     - `pilot_point_underattack_3_v1`
     - `pilot_point_underattack_3_v2`
     - `pilot_point_underattack_3_v3`
   - 来源字段：
     - `pilot_point_underattack_1_v1`：`["english"]`
     - `pilot_point_underattack_1_v2`：`["english"]`
     - `pilot_point_underattack_1_v3`：`["english"]`
     - `pilot_point_underattack_2_v1`：`["english"]`
     - `pilot_point_underattack_2_v2`：`["english"]`
     - `pilot_point_underattack_2_v3`：`["english"]`
     - `pilot_point_underattack_3_v1`：`["english"]`
     - `pilot_point_underattack_3_v2`：`["english"]`
     - `pilot_point_underattack_3_v3`：`["english"]`

10. `pilot_reinforcements_air_ally`

   - 组键：`pilot_reinforcements_air_ally`
   - 基础名称：`pilot_reinforcements_air_ally`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_reinforcements_air_ally_v1`
     - `pilot_reinforcements_air_ally_v2`
     - `pilot_reinforcements_air_ally_v3`
   - 来源字段：
     - `pilot_reinforcements_air_ally_v1`：`["english"]`
     - `pilot_reinforcements_air_ally_v2`：`["english"]`
     - `pilot_reinforcements_air_ally_v3`：`["english"]`

11. `pilot_reinforcements_air_enemy`

   - 组键：`pilot_reinforcements_air_enemy`
   - 基础名称：`pilot_reinforcements_air_enemy`
   - 命名类型：`v_suffix`
   - 成员数量：3
   - `module`：`radio`
   - `category`：**缺失**
   - 其他字段：无
   - 成员（JSON 原始顺序）：
     - `pilot_reinforcements_air_enemy_v1`
     - `pilot_reinforcements_air_enemy_v2`
     - `pilot_reinforcements_air_enemy_v3`
   - 来源字段：
     - `pilot_reinforcements_air_enemy_v1`：`["english"]`
     - `pilot_reinforcements_air_enemy_v2`：`["english"]`
     - `pilot_reinforcements_air_enemy_v3`：`["english"]`

## 5. Bank 完整分组

### 5.1 根对象元数据

- `schema_version`：`1`
- `module`：`bank`
- `source_directory`（仅供生成审计，运行时不读取）：`<external-war-thunder-sound-directory>`
- 其他根字段：无

### 5.2 common

- 前缀：`_crew_dialogs_common_`
- 类别其他字段：无

1. `common / cz`

   - 国家代码：`cz`
   - assets 文件：`_crew_dialogs_common_cz.assets.bank`
   - main 文件：`_crew_dialogs_common_cz.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

2. `common / de`

   - 国家代码：`de`
   - assets 文件：`_crew_dialogs_common_de.assets.bank`
   - main 文件：`_crew_dialogs_common_de.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

3. `common / en`

   - 国家代码：`en`
   - assets 文件：`_crew_dialogs_common_en.assets.bank`
   - main 文件：`_crew_dialogs_common_en.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

4. `common / fr`

   - 国家代码：`fr`
   - assets 文件：`_crew_dialogs_common_fr.assets.bank`
   - main 文件：`_crew_dialogs_common_fr.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

5. `common / hu`

   - 国家代码：`hu`
   - assets 文件：`_crew_dialogs_common_hu.assets.bank`
   - main 文件：`_crew_dialogs_common_hu.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

6. `common / it`

   - 国家代码：`it`
   - assets 文件：`_crew_dialogs_common_it.assets.bank`
   - main 文件：`_crew_dialogs_common_it.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

7. `common / jp`

   - 国家代码：`jp`
   - assets 文件：`_crew_dialogs_common_jp.assets.bank`
   - main 文件：`_crew_dialogs_common_jp.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

8. `common / ko`

   - 国家代码：`ko`
   - assets 文件：`_crew_dialogs_common_ko.assets.bank`
   - main 文件：`_crew_dialogs_common_ko.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

9. `common / pl`

   - 国家代码：`pl`
   - assets 文件：`_crew_dialogs_common_pl.assets.bank`
   - main 文件：`_crew_dialogs_common_pl.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

10. `common / pt`

   - 国家代码：`pt`
   - assets 文件：`_crew_dialogs_common_pt.assets.bank`
   - main 文件：`_crew_dialogs_common_pt.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

11. `common / ru`

   - 国家代码：`ru`
   - assets 文件：`_crew_dialogs_common_ru.assets.bank`
   - main 文件：`_crew_dialogs_common_ru.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

12. `common / sp`

   - 国家代码：`sp`
   - assets 文件：`_crew_dialogs_common_sp.assets.bank`
   - main 文件：`_crew_dialogs_common_sp.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

13. `common / sr`

   - 国家代码：`sr`
   - assets 文件：`_crew_dialogs_common_sr.assets.bank`
   - main 文件：`_crew_dialogs_common_sr.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

14. `common / th`

   - 国家代码：`th`
   - assets 文件：`_crew_dialogs_common_th.assets.bank`
   - main 文件：`_crew_dialogs_common_th.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

15. `common / tr`

   - 国家代码：`tr`
   - assets 文件：`_crew_dialogs_common_tr.assets.bank`
   - main 文件：`_crew_dialogs_common_tr.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

16. `common / vi`

   - 国家代码：`vi`
   - assets 文件：`_crew_dialogs_common_vi.assets.bank`
   - main 文件：`_crew_dialogs_common_vi.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

17. `common / zh`

   - 国家代码：`zh`
   - assets 文件：`_crew_dialogs_common_zh.assets.bank`
   - main 文件：`_crew_dialogs_common_zh.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

### 5.3 ground

- 前缀：`_crew_dialogs_ground_`
- 类别其他字段：无

1. `ground / ar`

   - 国家代码：`ar`
   - assets 文件：`_crew_dialogs_ground_ar.assets.bank`
   - main 文件：`_crew_dialogs_ground_ar.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

2. `ground / cz`

   - 国家代码：`cz`
   - assets 文件：`_crew_dialogs_ground_cz.assets.bank`
   - main 文件：`_crew_dialogs_ground_cz.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

3. `ground / de`

   - 国家代码：`de`
   - assets 文件：`_crew_dialogs_ground_de.assets.bank`
   - main 文件：`_crew_dialogs_ground_de.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

4. `ground / en`

   - 国家代码：`en`
   - assets 文件：`_crew_dialogs_ground_en.assets.bank`
   - main 文件：`_crew_dialogs_ground_en.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

5. `ground / en_au`

   - 国家代码：`en_au`
   - assets 文件：`_crew_dialogs_ground_en_au.assets.bank`
   - main 文件：`_crew_dialogs_ground_en_au.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

6. `ground / en_us`

   - 国家代码：`en_us`
   - assets 文件：`_crew_dialogs_ground_en_us.assets.bank`
   - main 文件：`_crew_dialogs_ground_en_us.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

7. `ground / en_za`

   - 国家代码：`en_za`
   - assets 文件：`_crew_dialogs_ground_en_za.assets.bank`
   - main 文件：`_crew_dialogs_ground_en_za.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

8. `ground / fi`

   - 国家代码：`fi`
   - assets 文件：`_crew_dialogs_ground_fi.assets.bank`
   - main 文件：`_crew_dialogs_ground_fi.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

9. `ground / fr`

   - 国家代码：`fr`
   - assets 文件：`_crew_dialogs_ground_fr.assets.bank`
   - main 文件：`_crew_dialogs_ground_fr.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

10. `ground / gl`

   - 国家代码：`gl`
   - assets 文件：`_crew_dialogs_ground_gl.assets.bank`
   - main 文件：`_crew_dialogs_ground_gl.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

11. `ground / he`

   - 国家代码：`he`
   - assets 文件：`_crew_dialogs_ground_he.assets.bank`
   - main 文件：`_crew_dialogs_ground_he.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

12. `ground / hi`

   - 国家代码：`hi`
   - assets 文件：`_crew_dialogs_ground_hi.assets.bank`
   - main 文件：`_crew_dialogs_ground_hi.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

13. `ground / hu`

   - 国家代码：`hu`
   - assets 文件：`_crew_dialogs_ground_hu.assets.bank`
   - main 文件：`_crew_dialogs_ground_hu.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

14. `ground / it`

   - 国家代码：`it`
   - assets 文件：`_crew_dialogs_ground_it.assets.bank`
   - main 文件：`_crew_dialogs_ground_it.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

15. `ground / jp`

   - 国家代码：`jp`
   - assets 文件：`_crew_dialogs_ground_jp.assets.bank`
   - main 文件：`_crew_dialogs_ground_jp.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

16. `ground / ko`

   - 国家代码：`ko`
   - assets 文件：`_crew_dialogs_ground_ko.assets.bank`
   - main 文件：`_crew_dialogs_ground_ko.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

17. `ground / lt`

   - 国家代码：`lt`
   - assets 文件：`_crew_dialogs_ground_lt.assets.bank`
   - main 文件：`_crew_dialogs_ground_lt.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

18. `ground / nl`

   - 国家代码：`nl`
   - assets 文件：`_crew_dialogs_ground_nl.assets.bank`
   - main 文件：`_crew_dialogs_ground_nl.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

19. `ground / nw`

   - 国家代码：`nw`
   - assets 文件：`_crew_dialogs_ground_nw.assets.bank`
   - main 文件：`_crew_dialogs_ground_nw.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

20. `ground / pl`

   - 国家代码：`pl`
   - assets 文件：`_crew_dialogs_ground_pl.assets.bank`
   - main 文件：`_crew_dialogs_ground_pl.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

21. `ground / pt`

   - 国家代码：`pt`
   - assets 文件：`_crew_dialogs_ground_pt.assets.bank`
   - main 文件：`_crew_dialogs_ground_pt.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

22. `ground / ru`

   - 国家代码：`ru`
   - assets 文件：`_crew_dialogs_ground_ru.assets.bank`
   - main 文件：`_crew_dialogs_ground_ru.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

23. `ground / sm_de`

   - 国家代码：`sm_de`
   - assets 文件：`_crew_dialogs_ground_sm_de.assets.bank`
   - main 文件：`_crew_dialogs_ground_sm_de.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

24. `ground / sm_jp`

   - 国家代码：`sm_jp`
   - assets 文件：`_crew_dialogs_ground_sm_jp.assets.bank`
   - main 文件：`_crew_dialogs_ground_sm_jp.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

25. `ground / sm_ru`

   - 国家代码：`sm_ru`
   - assets 文件：`_crew_dialogs_ground_sm_ru.assets.bank`
   - main 文件：`_crew_dialogs_ground_sm_ru.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

26. `ground / sm_uk`

   - 国家代码：`sm_uk`
   - assets 文件：`_crew_dialogs_ground_sm_uk.assets.bank`
   - main 文件：`_crew_dialogs_ground_sm_uk.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

27. `ground / sm_us`

   - 国家代码：`sm_us`
   - assets 文件：`_crew_dialogs_ground_sm_us.assets.bank`
   - main 文件：`_crew_dialogs_ground_sm_us.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

28. `ground / sm_zh`

   - 国家代码：`sm_zh`
   - assets 文件：`_crew_dialogs_ground_sm_zh.assets.bank`
   - main 文件：`_crew_dialogs_ground_sm_zh.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

29. `ground / sp`

   - 国家代码：`sp`
   - assets 文件：`_crew_dialogs_ground_sp.assets.bank`
   - main 文件：`_crew_dialogs_ground_sp.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

30. `ground / sr`

   - 国家代码：`sr`
   - assets 文件：`_crew_dialogs_ground_sr.assets.bank`
   - main 文件：`_crew_dialogs_ground_sr.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

31. `ground / sv`

   - 国家代码：`sv`
   - assets 文件：`_crew_dialogs_ground_sv.assets.bank`
   - main 文件：`_crew_dialogs_ground_sv.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

32. `ground / th`

   - 国家代码：`th`
   - assets 文件：`_crew_dialogs_ground_th.assets.bank`
   - main 文件：`_crew_dialogs_ground_th.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

33. `ground / tr`

   - 国家代码：`tr`
   - assets 文件：`_crew_dialogs_ground_tr.assets.bank`
   - main 文件：`_crew_dialogs_ground_tr.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

34. `ground / vi`

   - 国家代码：`vi`
   - assets 文件：`_crew_dialogs_ground_vi.assets.bank`
   - main 文件：`_crew_dialogs_ground_vi.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

35. `ground / zh`

   - 国家代码：`zh`
   - assets 文件：`_crew_dialogs_ground_zh.assets.bank`
   - main 文件：`_crew_dialogs_ground_zh.bank`
   - 是否完整配对：`true`
   - 缺失角色：`[]`
   - 其他字段：无

## 6. 未分类项目

### 6.1 车组：3 组、8 个成员

- `voice_message_commander_night_vision_off`
- `voice_message_commander_night_vision_on`
- `voice_message_commander_target_prem`

这三组均有 `module: crew`、合法 `type` 和非空 `names`，仅缺少 `category`。`CrewNameRepository` 可以正常精确识别它们；语音处理页会识别基础组，但不能据此自动切换到七个车组分类之一。

### 6.2 无线电：11 组、75 个成员

- `pilot_base_destroyed_ally`
- `pilot_base_destroyed_enemy`
- `pilot_base_underattack`
- `pilot_capture_ground_ally`
- `pilot_capture_ground_enemy`
- `pilot_mission_complete`
- `pilot_mission_fail`
- `pilot_mission_start_add`
- `pilot_point_underattack`
- `pilot_reinforcements_air_ally`
- `pilot_reinforcements_air_enemy`

这些组均有 `module: radio`、合法类型、非空成员和来源审计字段，仅缺少 `category`。无线电复制页不依赖分类，因此复制逻辑仍可使用；语音处理页不会自动切换到 `additional_01`、`态势播报` 或 `信息`。

## 7. 异常、重复项和数据提示

### 7.1 未发现的问题

- 没有组内重复成员。
- 没有同一完整名称出现在多个项目组。
- 没有仅大小写不同的名称冲突。
- 没有同一基础名称跨越多个分类。
- 没有缺失 `module` 的车组或无线电组；模块值均与所在 JSON 一致。
- 没有空 `names`、单成员项目组或带受支持音频扩展名的成员名称。
- 没有成员脱离其基础名称，也没有类型正则不匹配。
- 所有成员均已按自然数字顺序保存。
- 没有混用前导零的坐标结构。
- 车组与无线电两个 JSON 没有相同的完整成员名称，也没有基于 `module` 字段发现模块串用。
- 无线电每个 `sources` 键均与真实成员对应。
- Bank 没有重复文件名、大小写冲突、不可解析角色或残缺国家组；52 个国家组的 `complete`、`missing_roles` 与实际 `assets/main` 字段一致。

### 7.2 分类字段缺失

- 车组缺失分类：3 组，详见 6.1。
- 无线电缺失分类：11 组，详见 6.2。
- 这是当前唯一会直接影响语音处理分类路由的结构问题。

### 7.3 同一基础名称使用两个组键

`voice_message_driver_engine_stalled` 被有意拆为两个项目组：

- `voice_message_driver_engine_stalled__v1_layers`：`double`，成员为 `_v1_1`、`_v1_2`、`_v1_3`。
- `voice_message_driver_engine_stalled__v2_v3`：`single`，成员为 `_v2`、`_v3`。

两个组没有重复完整名称，并且都属于 `driver`。这是已确认的特殊业务拆组，不应按普通同基础名称规则自动合并。严格从第二组单独检查时会提示缺少 `_v1`，但 `_v1` 实际是另一组的双层结构，因此本报告只记录提示，不建议自动补号。

### 7.4 编号矩阵缺口提示

以下名称均真实存在于 JSON，`type` 也与名称后缀结构一致；这里只根据现有二维坐标的矩形范围提示空位，不代表空位对应的文件一定应当存在：

- `voice_message_commander_shovel_off` 当前只有 `_v2_2`、`_v2_3`。若按从 1 开始的矩形看，缺少整个 `v1` 层及 `_v2_1`。
- `voice_message_commander_shovel_on` 当前有 `_v1_1`、`_v1_2`、`_v1_3`、`_v2_1`。若按矩形看，缺少 `_v2_2`、`_v2_3`。
- `voice_message_driver_engine_stalled__v2_v3` 单独看从 `v2` 开始，但这是上一节所述特殊拆组。

无线电的 `v_suffix`、`v_matrix_suffix` 和 `matrix_suffix` 组未发现坐标空位、额外坐标或不连续矩阵。编号缺口不会被程序自动补齐。

### 7.5 程序代码与 JSON 字段适配

- `CrewNameRepository` 要求每组必须有合法 `type` 和 `names`，支持当前 `single`、`double`、`mixed`、`v_suffix`、`matrix_suffix`、`v_matrix_suffix`；它读取可选 `base_name`，但不使用 `module`、`category` 或 `sources`。
- `CrewNameRepository` 会拒绝跨组重复的完整名称，当前数据可正常加载。
- `ProjectGroupRepository` 要求 `names` 存在，读取 `base_name/module/category`，不读取 `type` 和 `sources`。若 `module` 缺失，会按来源 JSON 回退为 `crew` 或 `radio`；若 `category` 缺失，则保留为 `None`。
- `ProjectGroupRepository` 当前对重复完整名称采用字典后写覆盖，而不是抛出异常。当前数据没有重复，因此没有实际覆盖；建议未来增加显式重复校验。
- `BankNameRepository` 读取 `categories → countries → assets/main`，不会主动验证 `complete` 和 `missing_roles`。当前两个状态字段与实际角色完全一致，因此不会产生运行差异。
- 任何车组或无线电组若缺少 `names`，会在语音处理页面构造仓库时触发 `KeyError`，可能阻止页面初始化；当前不存在这种数据。

## 8. 语音处理页面适配结果

1. **能否从完整成员名称找到基础项目组：能。** `ProjectGroupRepository` 为车组和无线电的每个完整成员建立精确索引，返回 `base_name`、模块、分类和该组全部成员。
2. **是否正确取得 `module`：是。** 当前所有组都显式记录正确模块；字段缺失时仓库还会根据来源 JSON 使用 `crew` 或 `radio` 默认值。
3. **是否正确取得 `category`：已分类组可以。** 车组 3 组、无线电 11 组缺失分类，查询结果的 `category` 为 `None`。
4. **点击 `driver` 时是否只查询 `driver`：目录扫描是，名称查询不是。** 分类按钮把当前项目目录切换到 `车组/driver`，完成度只扫描该目录；粘贴名称的精确索引覆盖所有车组和无线电组，命中其他已分类组时会自动切换模块和分类。
5. **是否会错误展示全部项目组：不会。** 页面没有全库项目组列表，只展示当前输入命中的一个组及该组的已制作/待制作状态。
6. **是否能识别 `single`、`double`、`mixed`：能处理其成员，但不解释类型。** 语音处理页直接使用 JSON 的真实 `names` 元组，因此三种类型和无线电三种类型都能统计；页面不根据 `type` 猜测或生成成员。
7. **是否支持带扩展名输入：支持。** 对 `.wav/.flac/.ogg/.mp3/.m4a/.aac/.opus` 大小写不敏感，只去掉最后一个受支持扩展名。未知扩展名会保留在查询文本中，通常无法命中。
8. **是否支持完整路径：支持。** Windows 运行时使用 `Path(...).name` 取得末级文件名，再按上述规则去扩展名。
9. **字段缺失的界面结果：** `module` 缺失时使用来源默认模块；`category` 缺失时能识别组但保持用户当前分类，并提示未分类；`names` 缺失会导致仓库构造异常；`type` 缺失不影响语音处理页，但会使复制模块的 `CrewNameRepository` 拒绝加载。
10. **右侧已制作/待制作统计的数据来源：** 只使用当前命中 `ProjectGroup.names`，并扫描当前项目根目录下当前模块/分类目录中的真实受支持音频文件。同名多格式按一个逻辑名称计数，未命中的其他项目组不会混入统计。

## 9. 建议修改项（本次未执行）

1. 根据真实参考目录或人工业务确认，为车组 3 个和无线电 11 个未分类组补充 `category`；不要仅凭名称猜测。
2. 在 `ProjectGroupRepository` 中加入与复制仓库相同的跨组完整名称重复检查，避免未来静默覆盖。
3. 在数据生成校验中保留二维矩阵缺口提示，同时为 `shovel_off`、`shovel_on` 和 `driver_engine_stalled` 建立明确例外或审计说明，避免误补不存在的文件。
4. 资源构建流程可增加源 JSON 与 QRC 内嵌内容哈希检查，防止修改数据后忘记重新生成 `resources_rc.py`。
5. Bank 仓库可在加载时验证 `complete/missing_roles` 与 `assets/main` 一致，避免未来元数据与实际角色字段分歧。

以上建议均未在本次只读审计中执行。
