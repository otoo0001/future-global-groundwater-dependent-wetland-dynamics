# import numpy as np
# import matplotlib.pyplot as plt

# wtd_labels = ["0.1", "1", "2", "3", "4", "5", "6", "7", "8"]
# sat_labels = ["0.75", "0.5", "0.25"]

# # ---------------------------------------------------------------------------
# # Sensitivity heatmaps
# # ---------------------------------------------------------------------------
# # Rows top-to-bottom: satAreaFrac 0.75, 0.5, 0.25
# precision = np.array([
#     [0.55, 0.75, 0.82, 0.83, 0.83, 0.83, 0.82, 0.82, 0.82],
#     [0.65, 0.76, 0.81, 0.81, 0.80, 0.79, 0.78, 0.77, 0.76],
#     [0.65, 0.79, 0.80, 0.78, 0.77, 0.75, 0.74, 0.73, 0.72],
# ])
# recall = np.array([
#     [0.00, 0.02, 0.05, 0.06, 0.07, 0.08, 0.09, 0.09, 0.10],
#     [0.02, 0.09, 0.20, 0.26, 0.31, 0.34, 0.36, 0.38, 0.40],
#     [0.03, 0.13, 0.27, 0.37, 0.43, 0.47, 0.50, 0.53, 0.55],
# ])
# f1 = np.array([
#     [0.01, 0.04, 0.09, 0.12, 0.14, 0.15, 0.16, 0.17, 0.17],
#     [0.04, 0.16, 0.32, 0.40, 0.45, 0.48, 0.50, 0.51, 0.52],
#     [0.05, 0.22, 0.41, 0.50, 0.55, 0.58, 0.60, 0.61, 0.62],
# ])

# # Keep WTD=5 (col 5), satAreaFrac=0.5 (row 1) at the script's pasted values
# precision[1, 5] = 0.88
# recall[1, 5] = 0.60
# f1[1, 5] = 0.71

# metrics = [("Precision", precision), ("Recall", recall), ("F1", f1)]

# fig, axes = plt.subplots(1, 3, figsize=(18, 4.5))

# for ax, (name, data) in zip(axes, metrics):
#     im = ax.imshow(data, cmap="RdBu", aspect="auto", vmin=0, vmax=1)
#     ax.set_title(name, fontweight="bold")
#     ax.set_xticks(range(len(wtd_labels)))
#     ax.set_xticklabels(wtd_labels)
#     ax.set_yticks(range(len(sat_labels)))
#     ax.set_yticklabels(sat_labels)
#     ax.set_xlabel("WTD threshold (m)")
#     ax.set_ylabel("satAreaFrac threshold")
#     for i in range(data.shape[0]):
#         for j in range(data.shape[1]):
#             val = data[i, j]
#             ax.text(j, i, f"{val:.2f}", ha="center", va="center",
#                     color="black" if 0.25 < val < 0.75 else "white", fontsize=9)
#     fig.colorbar(im, ax=ax, shrink=0.85)

# plt.tight_layout(rect=[0, 0, 1, 0.95])
# plt.savefig("gdw_sensitivity_prf.png", dpi=200, bbox_inches="tight")

# # ---------------------------------------------------------------------------
# # Bar plot
# # ---------------------------------------------------------------------------
# sat_panels = ["0.25", "0.5", "0.75"]

# rhodes_ref = 3350.0  # thousand km2, constant reference

# # Simulated GDW dryland area (thousand km2), per panel
# sim = {
#     "0.25": [206, 788, 2110, 3278, 4292, 5221, 6065, 6840, 7542],
#     "0.5":  [178, 544, 1279, 1928, 2489, 2991, 3434, 3829, 4176],
#     "0.75": [30, 135, 269, 382, 476, 561, 638, 705, 762],
# }

# x = np.arange(len(wtd_labels))
# width = 0.38

# fig, axes = plt.subplots(1, 3, figsize=(20, 6), sharey=True)


# for ax, sat in zip(axes, sat_panels):
#     ax.bar(x - width / 2, np.full(len(x), rhodes_ref), width,
#            label="Rhodes \u2229 GLWD reference", color="#ff7f0e")
#     ax.bar(x + width / 2, sim[sat], width,
#            label="Simulated GDW, drylands", color="#2ca02c")
#     ax.set_title(f"satAreaFrac > {sat}", fontweight="bold")
#     ax.set_xticks(x)
#     ax.set_xticklabels(wtd_labels)
#     ax.set_xlabel("WTD threshold (m)")
#     ax.set_ylim(0, 8200)
#     if sat == "0.25":
#         ax.set_ylabel("Wetland area (thousand km\u00b2)")
#         ax.legend(loc="upper left")

# plt.tight_layout(rect=[0, 0, 1, 0.95])
# plt.savefig("gdw_area_bars.png", dpi=200, bbox_inches="tight")

# plt.show()



import numpy as np
import matplotlib.pyplot as plt

wtd_labels = ["0.1", "1", "2", "3", "4", "5", "6", "7", "8"]
sat_labels = ["0.75", "0.5", "0.25"]

# Rows top-to-bottom: satAreaFrac 0.75, 0.5, 0.25
precision = np.array([
    [0.55, 0.75, 0.82, 0.83, 0.83, 0.83, 0.82, 0.82, 0.82],
    [0.65, 0.76, 0.81, 0.81, 0.80, 0.79, 0.78, 0.77, 0.76],
    [0.65, 0.79, 0.80, 0.78, 0.77, 0.75, 0.74, 0.73, 0.72],
])
recall = np.array([
    [0.00, 0.02, 0.05, 0.06, 0.07, 0.08, 0.09, 0.09, 0.10],
    [0.02, 0.09, 0.20, 0.26, 0.31, 0.34, 0.36, 0.38, 0.40],
    [0.03, 0.13, 0.27, 0.37, 0.43, 0.47, 0.50, 0.53, 0.55],
])
f1 = np.array([
    [0.01, 0.04, 0.09, 0.12, 0.14, 0.15, 0.16, 0.17, 0.17],
    [0.04, 0.16, 0.32, 0.40, 0.45, 0.48, 0.50, 0.51, 0.52],
    [0.05, 0.22, 0.41, 0.50, 0.55, 0.58, 0.60, 0.61, 0.62],
])

metrics = [("Precision", precision), ("Recall", recall), ("F1", f1)]

fig, axes = plt.subplots(1, 3, figsize=(18, 4.5))

for ax, (name, data) in zip(axes, metrics):
    im = ax.imshow(data, cmap="RdBu", aspect="auto", vmin=0, vmax=1)
    ax.set_title(name, fontweight="bold")
    ax.set_xticks(range(len(wtd_labels)))
    ax.set_xticklabels(wtd_labels)
    ax.set_yticks(range(len(sat_labels)))
    ax.set_yticklabels(sat_labels)
    ax.set_xlabel("WTD threshold (m)")
    ax.set_ylabel("satAreaFrac threshold")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            val = data[i, j]
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    color="black" if 0.25 < val < 0.75 else "white", fontsize=9)
    fig.colorbar(im, ax=ax, shrink=0.85)

plt.tight_layout(rect=[0, 0, 1, 0.95])
plt.savefig("gdw_sensitivity_prf.png", dpi=200, bbox_inches="tight")
plt.show()