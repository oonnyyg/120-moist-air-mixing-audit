# 湿空气混合核算工具（离线，Python 标准库）

按**干空气质量**核算多股空气混合后的水汽与能量收支。仅做工况核算，
不做设备选型，也不模拟真实控制或凝水过程。

## 配置格式（JSON）

```json
{
  "property_table": {
    "total_pressure_kpa": 101.325,
    "temperatures_c": [0, 10, 20, 30, 40],
    "saturation_pressures_kpa": [0.6112, 1.2281, 2.3392, 4.2460, 7.3849]
  },
  "schemes": [
    {
      "name": "two-stream",
      "inlets": [
        {"label": "a", "temperature_c": 10, "relative_humidity": 0.8,
         "dry_air_flow_kg_s": 1.0},
        {"label": "b", "temperature_c": 30, "relative_humidity": 0.4,
         "dry_air_flow_kg_s": 2.0}
      ]
    }
  ]
}
```

- `temperatures_c` 与 `saturation_pressures_kpa` 均须**严格递增**、数值有限，
  至少两点；饱和水汽压为正。
- `total_pressure_kpa` 为正，且必须**高于表中所有饱和压**。
- 每个入口：温度摄氏度；相对湿度无量纲、取 `[0,1]`；
  `dry_air_flow_kg_s` 为干空气质量流量，必须为正（单位可统一替换，如 kg/h）。
- 混合反求得到的温度若超出表范围，该方案判为无效并提示扩充物性表。

示例：`examples/config.json`。

## 命令行

```bash
python -m moist_air.cli examples/config.json \
    --csv examples/out.csv --json examples/out.json
```

- CSV：每个方案一行的工况汇总表（混合温度、相对湿度、含湿量、焓、残差等）。
- JSON：每个方案的混合状态、逐入口状态与三项收支残差。
- 单个方案无效（含入口越界、数值非法、结果超表等）会**独立报告原因**，
  不阻断其他方案。

状态取值：`valid`（有效）、`condensation_required`（混合后过饱和，需凝露
处理）、`invalid`（方案本身非法）。

## 公式与单位

所有入口共用同一总压与同一张饱和压物性表。温度 `t` 为摄氏度（°C），
压力为千帕（kPa），流量以干空气计（默认 kg/s），焓为每千克干空气千焦
（kJ/kg_da），含湿量为 kg 水 / kg 干空气。

1. 饱和水汽压：对物性表做**分段线性插值** `p_ws(t)`；越界或非有限值拒绝。
2. 水汽分压：`p_w = φ · p_ws(t)`，`φ` 为 0–1 的相对湿度。
3. 含湿量：
   `w = 0.621945 · p_w / (p − p_w)`。
4. 焓（每千克干空气）：
   `h = 1.006 · t + w · (2501 + 1.86 · t)` kJ/kg_da。
5. 混合（按干空气流量 `m_da,i` 加权，**不直接平均温度或湿度**）：
   - `m_da,mix = Σ m_da,i`
   - `w_mix = Σ(m_da,i · w_i) / m_da,mix`
   - `h_mix = Σ(m_da,i · h_i) / m_da,mix`
6. 反求混合工况：
   - 温度由焓式反解：
     `t_mix = (h_mix − 2501 · w_mix) / (1.006 + 1.86 · w_mix)`；
   - 水汽分压：`p_w,mix = p · w_mix / (0.621945 + w_mix)`；
   - 饱和压查表：`p_ws,mix = p_ws(t_mix)`；
   - 相对湿度：`φ_mix = p_w,mix / p_ws,mix`。
7. 过饱和：若 `φ_mix > 1`，标记 `condensation_required`。**不**把相对湿度
   截成 1 冒充有效工况；本工具不模拟凝水，凝露需另行处理。

## 收支残差

JSON 报告给出干空气、水汽、焓三项流量平衡残差（入口合计 − 混合出口）：

- 干空气：kg/s
- 水汽：kg/s（`Σ m_da·w − m_da,mix·w_mix`）
- 焓：kW（`Σ m_da·h − m_da,mix·h_mix`）

加权求和使用 `math.fsum`，正常工况下残差应为机器精度量级的零。

## 测试

```bash
python -m unittest tests.test_moist_air -v
```

覆盖：插值与表校验、干空气入口（φ=0）、20 °C/50 % 参考点、不同含湿量
混合的加权与反求、单入口自洽、过饱和混合标记、无效方案隔离及 CLI 导出。
