"""
step2_visualization.py
Dual-Column Interactive Biomarker Surveillance & Decision Support.
Left: Scrollable stream of 11 primary biomarker trend graphs.
Right: Collapsible, plain-English NASA countermeasures & guidance.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.widgets import Button

# ======================================================================
# SIMPLIFIED CLINICAL KNOWLEDGE BASE (NASA HRP RESEARCH)
# Emergency protocols removed; explanations simplified for clear review
# ======================================================================
CLINICAL_KNOWLEDGE_BASE = {
    "BM01_WBC": {
        "Title": "1. White Blood Cells (WBC)",
        "Metric_Name": "WBC Count",
        "Unit": "10^9 cells/L",
        "RIDGE_Hazard": "R - Space Radiation",
        "HRP_Risk": "Risk of Weakened Immunity & Sepsis",
        "Direction": "low",
        "Concern_Threshold": 4.2,
        "Life_Saving_Threshold": 3.0,
        "Clinical_Baseline": "4.5 - 11.0 x 10^9 cells/L",
        "Scientific_Source": (
            "NASA HRP Immunology (Crucian 2018; "
            "DOI: 10.3389/fimmu.2018.01437)"
        ),
        "Problem_Why": (
            "Deep space cosmic radiation damages bone marrow stem cells.\n"
            "This lowers white blood cell counts, leaving astronauts\n"
            "vulnerable to dangerous bacterial and fungal infections."
        ),
        "What_To_Do": [
            "• Shelter: Move to water-shielded quarters during storms.",
            "• Nutrition: Take antioxidants (carotenoids, NAC, folate).",
            "• Recovery: Enforce strict 8.5-hour sleep rest periods."
        ]
    },
    "BM02_Serum_Calcium": {
        "Title": "2. Serum Calcium (Blood)",
        "Metric_Name": "Serum Calcium",
        "Unit": "mg/dL",
        "RIDGE_Hazard": "G - Gravity Fields",
        "HRP_Risk": "Risk of Bone Breakdown & Hypercalcemia",
        "Direction": "high",
        "Concern_Threshold": 10.5,
        "Life_Saving_Threshold": 12.0,
        "Clinical_Baseline": "8.5 - 10.2 mg/dL (2.12 - 2.55 mmol/L)",
        "Scientific_Source": (
            "Endocrine Society (Carroll 2010); NASA HHC (Smith 2014)"
        ),
        "Problem_Why": (
            "In zero gravity, bones stop carrying weight and break down.\n"
            "Excess calcium floods into the bloodstream, which can cause\n"
            "heart rhythm disruptions and acute kidney calcification."
        ),
        "What_To_Do": [
            "• Resistance: Heavy ARED squats/deadlifts (45 min/day).",
            "• Aerobic: CEVIS cycle intervals (30 min at 75% VO2 max).",
            "• Hydration: Drink >2.5 liters/day with Potassium Citrate.",
            "• Medications: Bisphosphonate (Alendronate) + Vitamin D."
        ]
    },
    "BM03_IL6": {
        "Title": "3. Interleukin-6 (IL-6 / Inflammation)",
        "Metric_Name": "Serum IL-6 Concentration",
        "Unit": "pg/mL",
        "RIDGE_Hazard": "E - Hostile/Closed Environment",
        "HRP_Risk": "Risk of Systemic Inflammation & Viral Reactivation",
        "Direction": "high",
        "Concern_Threshold": 5.0,
        "Life_Saving_Threshold": 20.0,
        "Clinical_Baseline": "< 3.0 pg/mL (I4 baseline: 1.0 - 4.5 pg/mL)",
        "Scientific_Source": (
            "Nature Microgravity (Crucian 2020; "
            "DOI: 10.1038/s41526-020-00115-1)"
        ),
        "Problem_Why": (
            "Spaceflight stress triggers systemic immune inflammation\n"
            "and reactivates dormant viruses (like shingles or EBV),\n"
            "stressing blood vessels and causing immune exhaustion."
        ),
        "What_To_Do": [
            "• Nutrition: Eat anti-inflammatory Omega-3 fats (EPA/DHA).",
            "• Screening: Test saliva and blood strips for viral shedding.",
            "• Workload: Temporarily reduce intense physical duty; rest."
        ]
    },
    "BM04_Urine_Calcium": {
        "Title": "4. Urinary Calcium Excretion",
        "Metric_Name": "24h Urinary Calcium Excretion",
        "Unit": "mg/day",
        "RIDGE_Hazard": "G - Gravity Fields",
        "HRP_Risk": "Risk of Painful Kidney Stone Formation",
        "Direction": "high",
        "Concern_Threshold": 240.0,
        "Life_Saving_Threshold": 310.0,
        "Clinical_Baseline": "100 - 240 mg/day (hypercalciuria > 250)",
        "Scientific_Source": (
            "NASA Renal Stone Risk (Whitson 2001; "
            "DOI: 10.1016/S0022-5347)"
        ),
        "Problem_Why": (
            "Broken-down bone calcium is filtered through the kidneys.\n"
            "In zero gravity, slow-moving urine pools in the bladder and\n"
            "kidneys, rapidly forming painful calcium oxalate stones."
        ),
        "What_To_Do": [
            "• Alkalinization: Potassium Citrate to raise urine pH >6.5.",
            "• Fluid Push: Drink 2.5 to 3.0 liters of fluids daily.",
            "• Diet: Limit dietary sodium to reduce urinary calcium loss."
        ]
    },
    "BM05_Uromodulin": {
        "Title": "5. Kidney Stress Marker (LCN2 / NGAL)",
        "Metric_Name": "Urine LCN2 / NGAL",
        "Unit": "NPQ",
        "RIDGE_Hazard": "E - Hostile/Closed Environment",
        "HRP_Risk": "Risk of Kidney Tubular Irritation & Injury",
        "Direction": "high",
        "Concern_Threshold": 10.5,
        "Life_Saving_Threshold": 13.5,
        "Clinical_Baseline": "5.5 - 10.0 NPQ (Inspiration4 baseline)",
        "Scientific_Source": (
            "Nature SOMA Repository (Overbey 2024; "
            "DOI: 10.1038/s41586-024-07639-2)"
        ),
        "Problem_Why": (
            "Fluid shifts and mineral micro-crystals irritate\n"
            "delicate kidney tubules, spilling stress markers (LCN2)\n"
            "and increasing the risk of acute tubular damage."
        ),
        "What_To_Do": [
            "• Protect Kidneys: Discontinue NSAIDs (like Ibuprofen).",
            "• Rehydrate: Drink oral electrolyte replenishment packets.",
            "• Dipstick: Daily urine test strips for protein or blood."
        ]
    },
    "BM06_Heart_Rate": {
        "Title": "6. Resting Heart Rate (Pulse)",
        "Metric_Name": "Resting Heart Rate",
        "Unit": "bpm",
        "RIDGE_Hazard": "G - Gravity Fields",
        "HRP_Risk": "Risk of Cardiovascular Deconditioning",
        "Direction": "high",
        "Concern_Threshold": 85.0,
        "Life_Saving_Threshold": 110.0,
        "Clinical_Baseline": "55 - 75 bpm (resting adult baseline)",
        "Scientific_Source": (
            "Physiological Reviews (Hughson 2018; "
            "DOI: 10.1152/physrev.00014.2017)"
        ),
        "Problem_Why": (
            "Without gravity, fluids shift to the chest. The body sheds\n"
            "extra fluid, shrinking blood volume. The heart must pump\n"
            "noticeably faster to deliver enough oxygen to tissues."
        ),
        "What_To_Do": [
            "• Aerobic: CEVIS cycle intervals (30 min at 75% VO2 max).",
            "• Hydration: Astro-ade oral electrolyte packets.",
            "• Compression: Don thigh compression garments (30-40 mmHg)."
        ]
    },
    "BM07_Respiratory_Rate": {
        "Title": "7. Resting Breathing Rate (RR)",
        "Metric_Name": "Respiratory Rate",
        "Unit": "breaths/min",
        "RIDGE_Hazard": "E - Hostile/Closed Environment",
        "HRP_Risk": "Risk of Carbon Dioxide Pooling (Hypercapnia)",
        "Direction": "high",
        "Concern_Threshold": 18.0,
        "Life_Saving_Threshold": 24.0,
        "Clinical_Baseline": "12 - 16 breaths/min (resting adult)",
        "Scientific_Source": (
            "JOEM (Law 2014; DOI: 10.1097/JOM.0000000000000158)"
        ),
        "Problem_Why": (
            "In microgravity, exhaled air does not rise or disperse.\n"
            "Invisible bubbles of CO2 accumulate around sleeping crew,\n"
            "triggering headaches, air hunger, and rapid breathing."
        ),
        "What_To_Do": [
            "• Scrubbers: Check CDRA scrubbers (keep cabin CO2 < 2 mmHg).",
            "• Ventilation: Inspect duct fans to clear stagnant air.",
            "• Quiet Rest: 30 minutes of quiet rest to reduce CO2 output."
        ]
    },
    "BM08_PTT": {
        "Title": "8. Blood Vessel Transit Time (PTT)",
        "Metric_Name": "Pulse Transit Time",
        "Unit": "ms",
        "RIDGE_Hazard": "R - Space Radiation & G",
        "HRP_Risk": "Risk of Arterial Stiffening & Hypertension",
        "Direction": "low",
        "Concern_Threshold": 220.0,
        "Life_Saving_Threshold": 190.0,
        "Clinical_Baseline": "250 - 320 ms (healthy flexible arteries)",
        "Scientific_Source": (
            "AJP-Heart (Hughson 2016; DOI: 10.1152/ajpheart.00802.2015)"
        ),
        "Problem_Why": (
            "Radiation and upward blood pressure cause arterial walls to\n"
            "lose elasticity. Shorter transit time (low PTT) means walls\n"
            "have become stiff, elevating high blood pressure risk."
        ),
        "What_To_Do": [
            "• Cycling: CEVIS cycling to promote nitric oxide flow.",
            "• Antioxidants: Eat dietary polyphenols to protect vessels.",
            "• Blood Pressure: Confirm baseline seated BP with arm cuff."
        ]
    },
    "BM09_WASO": {
        "Title": "9. Sleep Fragmentation (WASO)",
        "Metric_Name": "Wake After Sleep Onset",
        "Unit": "min awake/night",
        "RIDGE_Hazard": "I - Isolation & Confinement",
        "HRP_Risk": "Risk of Chronic Fatigue & Attention Lapses",
        "Direction": "high",
        "Concern_Threshold": 50.0,
        "Life_Saving_Threshold": 85.0,
        "Clinical_Baseline": "< 30 min/night (sleep efficiency > 85%)",
        "Scientific_Source": (
            "The Lancet Neurology (Barger 2014; "
            "DOI: 10.1016/S1474-4422(14)70122-X)"
        ),
        "Problem_Why": (
            "Experiencing 16 sunrises a day and machine hum shatters\n"
            "circadian sleep rhythms, creating severe sleep debt,\n"
            "cognitive fatigue, and critical operational mistakes."
        ),
        "What_To_Do": [
            "• Lighting: Shift cabin dynamic lights to warm red (2700K).",
            "• Noise: Custom earplugs & noise-canceling headsets.",
            "• Schedule: Strict 8.5h sleep window; Melatonin as needed."
        ]
    },
    "BM10_ONSD": {
        "Title": "10. Optic Nerve Sheath Diameter (SANS)",
        "Metric_Name": "ONSD Ultrasound",
        "Unit": "mm",
        "RIDGE_Hazard": "G - Gravity Fields",
        "HRP_Risk": "Risk of Vision Changes (SANS) & Vein Clots",
        "Direction": "high",
        "Concern_Threshold": 5.2,
        "Life_Saving_Threshold": 5.8,
        "Clinical_Baseline": "4.0 - 5.0 mm (ultrasound limit 5.2 mm)",
        "Scientific_Source": (
            "NASA SANS Report (Stenger 2017); Crit Care (Geeraerts 2008)"
        ),
        "Problem_Why": (
            "Fluids floating headward pool in neck and brain veins,\n"
            "swelling optic nerve sheath. This causes blurry\n"
            "vision (SANS) and sluggish blood flow in jugular veins."
        ),
        "What_To_Do": [
            "• LBNP Suction: 30-min Lower Body Negative Pressure.",
            "• Thigh Cuffs: Wear Braslet venous thigh cuffs in day.",
            "• Avoid Straining: Avoid breath-holding during workouts."
        ]
    },
    "BM11_PERCLOS": {
        "Title": "11. Eye Closure / Fatigue (PERCLOS)",
        "Metric_Name": "Percent Eye Closure",
        "Unit": "%",
        "RIDGE_Hazard": "I & D - Isolation & Distance",
        "HRP_Risk": "Risk of Dangerous Microsleeps During Duties",
        "Direction": "high",
        "Concern_Threshold": 12.0,
        "Life_Saving_Threshold": 20.0,
        "Clinical_Baseline": "< 8.0% (alert, awake operator)",
        "Scientific_Source": (
            "FHWA / NASA Langley (Dinges 1998; Basner & Dinges 2011)"
        ),
        "Problem_Why": (
            "High workloads and cumulative sleep loss cause eyelids to\n"
            "droop and stay closed. This signals dangerous involuntary\n"
            "microsleeps during Canadarm2 robotics or spacewalks."
        ),
        "What_To_Do": [
            "• Stand Down: Pause safety-critical robotics and EVA tasks.",
            "• Power Nap: Schedule an immediate 45-minute rest nap.",
            "• Alertness: Test with PVT app; expose to blue light."
        ]
    }
}

# Column aliases for robust CSV matching
COL_ALIASES = {
    "BM02_Serum_Calcium": ["BM02_Serum_Calcium", "BM02_Glucose"],
    "BM03_IL6": ["BM03_IL6", "BM03_CRP"],
    "BM06_Heart_Rate": ["BM06_Heart_Rate", "BM06_RMSSD"]
}


# ======================================================================
# DUAL-COLUMN INTERACTIVE SURVEILLANCE & DECISION SUPPORT DASHBOARD
# ======================================================================
def launch_dual_column_dashboard(
        csv_path="Four_Astronauts_12_Biomarkers.csv"
):
    if not os.path.exists(csv_path):
        if os.path.exists("Unified_12_Biomarkers_Dataset.csv"):
            csv_path = "Unified_12_Biomarkers_Dataset.csv"
        else:
            raise FileNotFoundError(f"Cannot find dataset: '{csv_path}'")

    raw_df = pd.read_csv(csv_path)
    bms = list(CLINICAL_KNOWLEDGE_BASE.keys())

    crew_list = raw_df["Astronaut_ID"].unique().tolist()
    if not crew_list:
        crew_list = [
            "Astronaut 1", "Astronaut 2", "Astronaut 3", "Astronaut 4"
        ]

    current_crew = crew_list[0]
    top_index = 0
    selected_index = 0

    # Collapsible Section States: True = Expanded, False = Collapsed
    section_states = {
        "problem": True,
        "countermeasures": True,
        "thresholds": True
    }

    # Track clickable header bounding boxes in ax_help:
    header_click_targets = {}

    # 18.5 x 10.5 High-Resolution Dual-Column Dashboard
    fig = plt.figure(figsize=(18.5, 10.5), facecolor="#f8fafc")
    try:
        fig.canvas.manager.set_window_title(
            "NASA Medical Surveillance & Decision Support Dashboard"
        )
    except Exception:
        pass

    gs = gridspec.GridSpec(
        3, 2, width_ratios=[0.55, 0.45], figure=fig,
        hspace=0.38, wspace=0.16, left=0.06, right=0.98,
        top=0.88, bottom=0.06
    )

    axes_left = [fig.add_subplot(gs[i, 0]) for i in range(3)]
    ax_help = fig.add_subplot(gs[:, 1])

    # Top Control Bar
    ax_ast1 = fig.add_axes([0.06, 0.925, 0.088, 0.040])
    ax_ast2 = fig.add_axes([0.152, 0.925, 0.088, 0.040])
    ax_ast3 = fig.add_axes([0.244, 0.925, 0.088, 0.040])
    ax_ast4 = fig.add_axes([0.336, 0.925, 0.088, 0.040])

    ax_btn_up = fig.add_axes([0.435, 0.925, 0.075, 0.040])
    ax_btn_dn = fig.add_axes([0.515, 0.925, 0.075, 0.040])
    ax_btn_toggle = fig.add_axes([0.835, 0.925, 0.145, 0.040])

    btn_ast1 = Button(
        ax_ast1, "Astronaut 1", color="#e0f2fe", hovercolor="#bae6fd"
    )
    btn_ast2 = Button(
        ax_ast2, "Astronaut 2", color="#f1f5f9", hovercolor="#bae6fd"
    )
    btn_ast3 = Button(
        ax_ast3, "Astronaut 3", color="#f1f5f9", hovercolor="#bae6fd"
    )
    btn_ast4 = Button(
        ax_ast4, "Astronaut 4", color="#f1f5f9", hovercolor="#bae6fd"
    )
    btn_up = Button(
        ax_btn_up, "▲ Scroll Up", color="#e2e8f0", hovercolor="#cbd5e1"
    )
    btn_dn = Button(
        ax_btn_dn, "▼ Scroll Down", color="#e2e8f0", hovercolor="#cbd5e1"
    )
    btn_toggle = Button(
        ax_btn_toggle, "Collapse All",
        color="#e2e8f0", hovercolor="#cbd5e1"
    )

    all_buttons = [
        btn_ast1, btn_ast2, btn_ast3, btn_ast4,
        btn_up, btn_dn, btn_toggle
    ]
    for b in all_buttons:
        b.label.set_fontsize(10.5)
        b.label.set_fontweight("bold")

    # Helper function to get astronaut data series
    def get_series(ast_id, bm_key):
        sub_df = raw_df[raw_df["Astronaut_ID"] == ast_id]
        sub_df = sub_df.sort_values("Timepoint")
        target_col = bm_key
        if bm_key in COL_ALIASES:
            for alt in COL_ALIASES[bm_key]:
                if alt in sub_df.columns:
                    target_col = alt
                    break
        if target_col in sub_df.columns:
            y = pd.to_numeric(sub_df[target_col], errors="coerce").values
        else:
            y = np.array([])
        x = (
            sub_df["Timepoint"].values
            if not sub_df.empty else np.array([1, 2, 3, 4, 5])
        )
        return x, y

    # Render Left Biomarker Trend Subplots with BIGGER Fonts
    def render_left_plots():
        visible_bms = bms[top_index: top_index + 3]
        for i, ax in enumerate(axes_left):
            ax.clear()
            if i >= len(visible_bms):
                ax.axis("off")
                continue

            bm_key = visible_bms[i]
            abs_idx = top_index + i
            meta = CLINICAL_KNOWLEDGE_BASE[bm_key]
            x_vals, y_vals = get_series(current_crew, bm_key)
            valid_mask = (
                ~np.isnan(y_vals) if len(y_vals) > 0 else np.array([])
            )

            t_concern = meta["Concern_Threshold"]
            t_crit = meta["Life_Saving_Threshold"]

            all_y = (
                    [v for v in y_vals if not np.isnan(v)]
                    + [t_concern, t_crit]
            )
            y_min = min(all_y) * 0.76
            y_max = max(all_y) * 1.24
            if y_min == y_max:
                y_min -= 1.0
                y_max += 1.0

            # Shaded Clinical Zones
            if meta["Direction"] == "high":
                ax.axhspan(
                    y_min, t_concern, color="#dcfce7",
                    alpha=0.55, label="Safe"
                )
                ax.axhspan(
                    t_concern, t_crit, color="#fef9c3",
                    alpha=0.65, label="Concern"
                )
                ax.axhspan(
                    t_crit, y_max, color="#fee2e2",
                    alpha=0.60, label="Life-Saving"
                )
            else:
                ax.axhspan(
                    t_concern, y_max, color="#dcfce7",
                    alpha=0.55, label="Safe"
                )
                ax.axhspan(
                    t_crit, t_concern, color="#fef9c3",
                    alpha=0.65, label="Concern"
                )
                ax.axhspan(
                    y_min, t_crit, color="#fee2e2",
                    alpha=0.60, label="Life-Saving"
                )

            ax.axhline(
                t_concern, color="#d97706", linestyle="--",
                linewidth=1.6, alpha=0.9
            )
            ax.axhline(
                t_crit, color="#dc2626", linestyle="-",
                linewidth=1.8, alpha=0.9
            )

            if np.any(valid_mask):
                xv = x_vals[valid_mask]
                yv = y_vals[valid_mask]
                ax.plot(
                    xv, yv, color="#0284c7", marker="o", markersize=7.0,
                    linewidth=2.4, label="Readings"
                )

                if len(xv) >= 2:
                    poly = np.polyfit(xv, yv, 1)
                    ax.plot(
                        xv, np.polyval(poly, xv), color="#64748b",
                        linestyle=":", linewidth=1.5, alpha=0.85
                    )

                if meta["Direction"] == "high":
                    crit_pts = yv >= t_crit
                    concern_pts = (yv >= t_concern) & (yv < t_crit)
                else:
                    crit_pts = yv <= t_crit
                    concern_pts = (yv <= t_concern) & (yv > t_crit)

                if np.any(concern_pts):
                    ax.scatter(
                        xv[concern_pts], yv[concern_pts], color="#d97706",
                        s=100, zorder=6, edgecolors="white", marker="D"
                    )
                if np.any(crit_pts):
                    ax.scatter(
                        xv[crit_pts], yv[crit_pts], color="#dc2626",
                        s=140, zorder=7, edgecolors="white", marker="*"
                    )

            ax.set_ylim(y_min, y_max)
            ax.set_xticks(x_vals)
            ax.set_xticklabels(
                [f"TP{t}" for t in x_vals], color="#1e293b",
                fontsize=10.0, fontweight="bold"
            )
            ax.tick_params(axis="y", colors="#1e293b", labelsize=10.0)
            ax.tick_params(axis="x", colors="#1e293b", labelsize=10.0)
            ax.grid(
                True, color="#cbd5e1", alpha=0.7,
                linestyle="--", linewidth=0.8
            )

            # Highlight selected graph with active cyan border
            is_active = (abs_idx == selected_index)
            title_prefix = "[ACTIVE SELECTED] " if is_active else ""
            title_color = "#0369a1" if is_active else "#1e293b"
            border_color = "#0284c7" if is_active else "#94a3b8"
            border_width = 2.4 if is_active else 1.2

            for spine in ax.spines.values():
                spine.set_edgecolor(border_color)
                spine.set_linewidth(border_width)

            ax.set_facecolor("#f0fdfa" if is_active else "#ffffff")
            ax.set_title(
                f"{title_prefix}{meta['Title']}  [{meta['RIDGE_Hazard']}]",
                color=title_color, fontsize=11.5, fontweight="bold", pad=5
            )
            ax.set_ylabel(
                meta["Unit"], color="#334155",
                fontsize=10.5, fontweight="bold"
            )
            ax.legend(
                loc="upper right", fontsize=8.5, facecolor="#ffffff",
                edgecolor="#cbd5e1", framealpha=0.9
            )

    # Render Right Contextual Help Panel with Collapsible Sections
    def render_right_help():
        nonlocal header_click_targets
        header_click_targets.clear()

        ax_help.clear()
        ax_help.set_facecolor("#ffffff")
        ax_help.set_xlim(0, 1)
        ax_help.set_ylim(0, 1)
        ax_help.set_xticks([])
        ax_help.set_yticks([])

        for spine in ax_help.spines.values():
            spine.set_edgecolor("#0284c7")
            spine.set_linewidth(2.0)

        sel_key = bms[selected_index]
        meta = CLINICAL_KNOWLEDGE_BASE[sel_key]
        x_vals, y_vals = get_series(current_crew, sel_key)
        valid_y = [v for v in y_vals if not np.isnan(v)]

        # Header Badge
        ax_help.text(
            0.5, 0.965, "NASA CLINICAL DECISION SUPPORT & ACTION PLAN",
            ha="center", va="top", fontsize=12.5, fontweight="bold",
            color="#0369a1",
            bbox=dict(
                boxstyle="round,pad=0.35", facecolor="#e0f2fe",
                edgecolor="#0284c7", linewidth=1.4
            )
        )

        # Active Metric Title
        ax_help.text(
            0.05, 0.908, meta["Title"],
            ha="left", va="top", fontsize=13.5, fontweight="bold",
            color="#0f172a"
        )
        ax_help.text(
            0.05, 0.875,
            f"Hazard: {meta['RIDGE_Hazard']} | Risk: {meta['HRP_Risk']}",
            ha="left", va="top", fontsize=10.2, color="#475569"
        )

        # Astronaut Status Alert Box
        latest_val = valid_y[-1] if len(valid_y) > 0 else np.nan
        t_conc = meta["Concern_Threshold"]
        t_crit = meta["Life_Saving_Threshold"]

        if np.isnan(latest_val):
            stat_str = f"STATUS: {current_crew.upper()} - NO DATA RECORDED"
            bg_col, fg_col = "#f1f5f9", "#475569"
        else:
            if meta["Direction"] == "high":
                is_crit = latest_val >= t_crit
                is_conc = (latest_val >= t_conc) and (latest_val < t_crit)
            else:
                is_crit = latest_val <= t_crit
                is_conc = (latest_val <= t_conc) and (latest_val > t_crit)

            if is_crit:
                stat_str = (
                    f"STATUS: {current_crew.upper()} = {latest_val:.2f} "
                    f"{meta['Unit']}  [CRITICAL RED ALERT]"
                )
                bg_col, fg_col = "#fee2e2", "#dc2626"
            elif is_conc:
                stat_str = (
                    f"STATUS: {current_crew.upper()} = {latest_val:.2f} "
                    f"{meta['Unit']}  [YELLOW CONCERN ALERT]"
                )
                bg_col, fg_col = "#fef3c7", "#b45309"
            else:
                stat_str = (
                    f"STATUS: {current_crew.upper()} = {latest_val:.2f} "
                    f"{meta['Unit']}  [SAFE PHYSIOLOGICAL ZONE]"
                )
                bg_col, fg_col = "#dcfce7", "#15803d"

        ax_help.text(
            0.05, 0.835, stat_str, ha="left", va="top", fontsize=11.2,
            fontweight="bold", color=fg_col,
            bbox=dict(
                boxstyle="square,pad=0.32", facecolor=bg_col,
                edgecolor=fg_col, linewidth=1.1
            )
        )

        # Dynamic Vertical Layout Cursor
        cursor_y = 0.770

        # --------------------------------------------------------------
        # SECTION 1: THE PROBLEM (WHY THIS HAPPENS)
        # --------------------------------------------------------------
        is_p_exp = section_states["problem"]
        p_arrow = "▼" if is_p_exp else "▶"
        p_act = "Click to Collapse" if is_p_exp else "Click to Expand"
        header_p = f"{p_arrow}  1. THE PROBLEM   [{p_act}]"

        ax_help.text(
            0.05, cursor_y, header_p,
            ha="left", va="top", fontsize=11.8, fontweight="bold",
            color="#1e3a8a",
            bbox=dict(
                boxstyle="round,pad=0.28", facecolor="#eff6ff",
                edgecolor="#bfdbfe", linewidth=1.0
            )
        )
        header_click_targets["problem"] = (
            cursor_y - 0.045, cursor_y + 0.005
        )
        cursor_y -= 0.052

        if is_p_exp:
            ax_help.text(
                0.07, cursor_y, meta["Problem_Why"],
                ha="left", va="top", fontsize=11.0, color="#1e293b",
                linespacing=1.35
            )
            cursor_y -= 0.095
        else:
            cursor_y -= 0.015

        # --------------------------------------------------------------
        # SECTION 2: WHAT TO DO (COUNTERMEASURES & CARE)
        # --------------------------------------------------------------
        is_c_exp = section_states["countermeasures"]
        c_arrow = "▼" if is_c_exp else "▶"
        c_act = "Click to Collapse" if is_c_exp else "Click to Expand"
        header_c = f"{c_arrow}  2. WHAT TO DO   [{c_act}]"

        ax_help.text(
            0.05, cursor_y, header_c,
            ha="left", va="top", fontsize=11.8, fontweight="bold",
            color="#1e3a8a",
            bbox=dict(
                boxstyle="round,pad=0.28", facecolor="#eff6ff",
                edgecolor="#bfdbfe", linewidth=1.0
            )
        )
        header_click_targets["countermeasures"] = (
            cursor_y - 0.045, cursor_y + 0.005
        )
        cursor_y -= 0.052

        if is_c_exp:
            sec2_text = "\n".join(meta["What_To_Do"])
            ax_help.text(
                0.07, cursor_y, sec2_text,
                ha="left", va="top", fontsize=11.0, color="#1e293b",
                linespacing=1.38
            )
            cursor_y -= (len(meta["What_To_Do"]) * 0.040 + 0.035)
        else:
            cursor_y -= 0.015

        # --------------------------------------------------------------
        # SECTION 3: NORMAL RANGE & SAFETY THRESHOLDS
        # --------------------------------------------------------------
        is_t_exp = section_states["thresholds"]
        t_arrow = "▼" if is_t_exp else "▶"
        t_act = "Click to Collapse" if is_t_exp else "Click to Expand"
        header_t = f"{t_arrow}  3. NORMAL RANGE & THRESHOLDS   [{t_act}]"

        ax_help.text(
            0.05, cursor_y, header_t,
            ha="left", va="top", fontsize=11.8, fontweight="bold",
            color="#1e3a8a",
            bbox=dict(
                boxstyle="round,pad=0.28", facecolor="#eff6ff",
                edgecolor="#bfdbfe", linewidth=1.0
            )
        )
        header_click_targets["thresholds"] = (
            cursor_y - 0.045, cursor_y + 0.005
        )
        cursor_y -= 0.052

        if is_t_exp:
            thresh_text = (
                f"• Healthy Baseline: {meta['Clinical_Baseline']}\n"
                f"• Concern Level   : {meta['Concern_Threshold']} "
                f"{meta['Unit']} (Caution Alert)\n"
                f"• Critical Level  : {meta['Life_Saving_Threshold']} "
                f"{meta['Unit']} (Critical Alert)\n"
                f"• Scientific Ref  : {meta['Scientific_Source']}"
            )
            ax_help.text(
                0.07, cursor_y, thresh_text,
                ha="left", va="top", fontsize=10.5, color="#334155",
                linespacing=1.35
            )

        # Bottom Navigation & Interactivity Guide
        nav_text = (
            "Interactive Controls:\n"
            "• Click any Section Header above to Collapse or Expand it.\n"
            "• Use 'Toggle All' button (top right) to toggle cards.\n"
            "• Mouse Wheel or Up/Down buttons scroll through graphs.\n"
            "• Click any graph on left to inspect its clinical card."
        )
        ax_help.text(
            0.05, 0.088, nav_text, ha="left", va="top", fontsize=9.8,
            fontstyle="italic", color="#475569",
            bbox=dict(
                boxstyle="round,pad=0.35", facecolor="#f8fafc",
                edgecolor="#cbd5e1", linewidth=0.9
            )
        )

    # Master View Refresh
    def update_view():
        render_left_plots()
        render_right_help()
        btn_ast1.color = (
            "#bae6fd" if current_crew == crew_list[0] else "#f1f5f9"
        )
        btn_ast2.color = (
            "#bae6fd" if len(crew_list) > 1 and (
                    current_crew == crew_list[1]
            )
            else "#f1f5f9"
        )
        btn_ast3.color = (
            "#bae6fd" if len(crew_list) > 2 and (
                    current_crew == crew_list[2]
            )
            else "#f1f5f9"
        )
        btn_ast4.color = (
            "#bae6fd" if len(crew_list) > 3 and (
                    current_crew == crew_list[3]
            )
            else "#f1f5f9"
        )

        all_collapsed = not any(section_states.values())
        btn_toggle.label.set_text(
            "Expand All" if all_collapsed else "Collapse All"
        )

        fig.canvas.draw_idle()

    # Event Handlers
    def on_scroll(event):
        nonlocal top_index, selected_index
        if event.button == "down" or (
                hasattr(event, "step") and event.step < 0
        ):
            if top_index < len(bms) - 3:
                top_index += 1
            selected_index = min(len(bms) - 1, selected_index + 1)
            update_view()
        elif event.button == "up" or (
                hasattr(event, "step") and event.step > 0
        ):
            if top_index > 0:
                top_index -= 1
            selected_index = max(0, selected_index - 1)
            update_view()

    def on_click(event):
        nonlocal selected_index
        # Check if click was in a left plot
        for i, ax in enumerate(axes_left):
            if event.inaxes == ax:
                selected_index = top_index + i
                update_view()
                return

        # Check if click was on a collapsible section header in ax_help
        if event.inaxes == ax_help and event.ydata is not None:
            y = event.ydata
            for sec, (y_bot, y_top) in header_click_targets.items():
                if y_bot <= y <= y_top:
                    section_states[sec] = not section_states[sec]
                    update_view()
                    return

    def on_key(event):
        nonlocal top_index, selected_index
        if event.key in ["down", "pagedown", "right"]:
            if top_index < len(bms) - 3:
                top_index += 1
            selected_index = min(len(bms) - 1, selected_index + 1)
            update_view()
        elif event.key in ["up", "pageup", "left"]:
            if top_index > 0:
                top_index -= 1
            selected_index = max(0, selected_index - 1)
            update_view()

    # Button Callbacks
    def set_crew(name):
        nonlocal current_crew
        current_crew = name
        update_view()

    def scroll_up_action(event):
        nonlocal top_index, selected_index
        if top_index > 0:
            top_index -= 1
        selected_index = max(0, selected_index - 1)
        update_view()

    def scroll_dn_action(event):
        nonlocal top_index, selected_index
        if top_index < len(bms) - 3:
            top_index += 1
        selected_index = min(len(bms) - 1, selected_index + 1)
        update_view()

    def toggle_all_action(event):
        any_open = any(section_states.values())
        new_state = not any_open
        for k in section_states:
            section_states[k] = new_state
        update_view()

    btn_ast1.on_clicked(lambda e: set_crew(crew_list[0]))
    if len(crew_list) > 1:
        btn_ast2.on_clicked(lambda e: set_crew(crew_list[1]))
    if len(crew_list) > 2:
        btn_ast3.on_clicked(lambda e: set_crew(crew_list[2]))
    if len(crew_list) > 3:
        btn_ast4.on_clicked(lambda e: set_crew(crew_list[3]))

    btn_up.on_clicked(scroll_up_action)
    btn_dn.on_clicked(scroll_dn_action)
    btn_toggle.on_clicked(toggle_all_action)

    fig.canvas.mpl_connect("scroll_event", on_scroll)
    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)

    # Initial Render
    update_view()

    print("=" * 72)
    print("NASA MEDICAL SURVEILLANCE & CLINICAL DECISION SUPPORT")
    print("=" * 72)
    print("• Left Column  : Scroll through 11 biomarker trend graphs.")
    print("• Right Column : Collapsible countermeasures & guidance.")
    print("• Controls     : Click headers or 'Toggle All' button.")
    print("=" * 72)
    plt.show()


# ======================================================================
# ENTRY POINT
# ======================================================================
if __name__ == "__main__":
    target_csv = "Four_Astronauts_12_Biomarkers.csv"
    if not os.path.exists(target_csv):
        target_csv = "Unified_12_Biomarkers_Dataset.csv"
    launch_dual_column_dashboard(csv_path=target_csv)
