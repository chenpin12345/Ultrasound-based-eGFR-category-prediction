import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import re
from matplotlib import rcParams
try:
    from ._paths import reference
except ImportError:
    from _paths import reference

# ========================================
# Publication-Quality Settings
# ========================================
# Use Times New Roman or similar serif font for academic publications
rcParams['font.family'] = 'serif'
rcParams['font.serif'] = ['Times New Roman', 'DejaVu Serif']
rcParams['font.size'] = 10
rcParams['axes.labelsize'] = 11
rcParams['axes.titlesize'] = 12
rcParams['xtick.labelsize'] = 10
rcParams['ytick.labelsize'] = 10
rcParams['legend.fontsize'] = 10
rcParams['figure.titlesize'] = 12

# High-resolution settings for publication
rcParams['figure.dpi'] = 300
rcParams['savefig.dpi'] = 300
rcParams['savefig.bbox'] = 'tight'
rcParams['savefig.pad_inches'] = 0.1

# Professional styling
rcParams['axes.linewidth'] = 1.0
rcParams['grid.linewidth'] = 0.5
rcParams['lines.linewidth'] = 1.5
rcParams['patch.linewidth'] = 1.0

# ========================================
# Data Loading and Processing
# ========================================
csv_path = reference('metadata.csv')
df = pd.read_csv(csv_path)

def categorize_image(name):
    """Categorize images based on naming convention"""
    match = re.match(r"([0-9.]+)_", str(name))
    if not match:
        return "Unknown"
    
    val = float(match.group(1))
    if val < 15:
        return "<15"
    elif val < 30:
        return "15-29"
    elif val < 60:
        return "30-59"
    elif val < 90:
        return "60-89"
    else:
        return "≥90"

df["category"] = df["image_name"].apply(categorize_image)

# Define category order (ascending for better readability)
categories = ["<15", "15-29", "30-59", "60-89", "≥90"]

# ========================================
# Color Scheme for Publication
# ========================================
# Professional color palette (colorblind-friendly)
COLOR_PALETTE = {
    'box': '#666666',
    'median': '#000000',
    'male': '#333333',
    'female': '#999999',
    'grid': '#cccccc'        # Light gray for grid
}

# Ensure grid color is defined
GRID_COLOR = COLOR_PALETTE['grid']

# ========================================
# Figure 1: Image Feature Distributions
# ========================================
def plot_feature_boxplots(df, categories, output_path='figure1_features.png'):
    """
    Create publication-quality boxplots for image features
    """
    features = ["Length_px", "Contrast_Ratio"]
    feature_labels = {
        "Length_px": "Kidney Length (pixels)",
        "Contrast_Ratio": "Contrast Ratio"
    }
    
    # Create separate figures for each feature
    for idx, feature in enumerate(features):
        fig, ax = plt.subplots(figsize=(6, 4.5))
        
        # Prepare data
        data = [df.loc[df["category"] == c, feature].dropna() for c in categories]
        
        # Create boxplot
        bp = ax.boxplot(
            data,
            tick_labels=categories,
            patch_artist=True,
            widths=0.6,
            showfliers=True,
            flierprops=dict(marker='o', markerfacecolor='gray', markersize=3, 
                          linestyle='none', markeredgecolor='gray', alpha=0.5),
            boxprops=dict(facecolor=COLOR_PALETTE['box'], edgecolor='black', 
                         linewidth=1.0, alpha=0.7),
            medianprops=dict(color=COLOR_PALETTE['median'], linewidth=1.5),
            whiskerprops=dict(color='black', linewidth=1.0),
            capprops=dict(color='black', linewidth=1.0)
        )
        
        # Styling
        ax.set_xlabel('eGFR Categories (mL/min/1.73m²)', fontweight='normal')
        ax.set_ylabel(feature_labels[feature], fontweight='normal')
        ax.set_title(f'{feature_labels[feature]} Distribution Across eGFR Categories', 
                    fontweight='bold')
        
        # Grid
        ax.yaxis.grid(True, linestyle='--', alpha=0.3, color=COLOR_PALETTE['grid'])
        ax.set_axisbelow(True)
        
        # Spines
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        
        # Save individual figure
        individual_output = output_path.replace('.png', f'_{feature}.png')
        plt.savefig(individual_output, dpi=300, bbox_inches='tight')
        print(f"Figure saved: {individual_output}")
        plt.show()

# ========================================
# Figure 2: Age Distribution
# ========================================
def plot_age_distribution(df, categories, output_path='figure2_age.png'):
    """
    Create publication-quality boxplot for age distribution
    """
    fig, ax = plt.subplots(figsize=(6, 4.5))
    
    # Prepare data
    age_data = [df.loc[df["category"] == c, "age"].dropna() for c in categories]
    
    # Create boxplot
    bp = ax.boxplot(
        age_data,
        tick_labels=categories,
        patch_artist=True,
        widths=0.6,
        showfliers=True,
        flierprops=dict(marker='o', markerfacecolor='gray', markersize=3, 
                       linestyle='none', markeredgecolor='gray', alpha=0.5),
        boxprops=dict(facecolor=COLOR_PALETTE['box'], edgecolor='black', 
                     linewidth=1.0, alpha=0.7),
        medianprops=dict(color=COLOR_PALETTE['median'], linewidth=1.5),
        whiskerprops=dict(color='black', linewidth=1.0),
        capprops=dict(color='black', linewidth=1.0)
    )
    
    # Styling
    ax.set_xlabel('eGFR Categories (mL/min/1.73m²)', fontweight='normal')
    ax.set_ylabel('Age (years)', fontweight='normal')
    ax.set_title('Age Distribution Across eGFR Categories', fontweight='bold')
    
    # Grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.3, color=COLOR_PALETTE['grid'])
    ax.set_axisbelow(True)
    
    # Spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Figure 2 saved: {output_path}")
    plt.show()

# ========================================
# Figure 3: Gender Distribution
# ========================================
def plot_gender_distribution(df, categories, output_path='figure3_gender.png'):
    """
    Create publication-quality grouped bar chart for gender distribution
    """
    # Count gender by category
    gender_counts = df.groupby(["category", "gender"]).size().unstack(fill_value=0)
    gender_counts = gender_counts.reindex(categories)
    
    # Handle missing gender columns
    for g in ["男", "女"]:
        if g not in gender_counts.columns:
            gender_counts[g] = 0
    
    fig, ax = plt.subplots(figsize=(7, 4.5))
    
    x = np.arange(len(categories))
    width = 0.35
    
    # Create bars
    bars1 = ax.bar(x - width/2, gender_counts["男"], width, 
                   label='Male', color=COLOR_PALETTE['male'], 
                   edgecolor='black', linewidth=0.8, alpha=0.8)
    bars2 = ax.bar(x + width/2, gender_counts["女"], width, 
                   label='Female', color=COLOR_PALETTE['female'], 
                   edgecolor='black', linewidth=0.8, alpha=0.8)
    
    # Add value labels on bars
    def add_value_labels(bars):
        for bar in bars:
            height = bar.get_height()
            if height > 0:  # Only show non-zero values
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{int(height)}',
                       ha='center', va='bottom', fontsize=9)
    
    add_value_labels(bars1)
    add_value_labels(bars2)
    
    # Styling
    ax.set_xlabel('eGFR Categories (mL/min/1.73m²)', fontweight='normal')
    ax.set_ylabel('Number of Subjects', fontweight='normal')
    ax.set_title('Gender Distribution Across eGFR Categories', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.legend(frameon=True, edgecolor='black', fancybox=False)
    
    # Grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.3, color=COLOR_PALETTE['grid'])
    ax.set_axisbelow(True)
    
    # Spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    # Set y-axis to start from 0
    ax.set_ylim(bottom=0)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Figure 3 saved: {output_path}")
    plt.show()

# ========================================
# Combined Figure (Optional)
# ========================================
def plot_combined_figure(df, categories, output_path='figure_combined.png'):
    """
    Create a combined publication-quality figure with all plots
    """
    fig = plt.figure(figsize=(10, 8))
    gs = fig.add_gridspec(3, 2, hspace=0.35, wspace=0.3)
    
    features = ["Length_px", "Contrast_Ratio"]
    feature_labels = {
        "Length_px": "Length (pixels)",
        "Contrast_Ratio": "Contrast Ratio"
    }
    
    # (a) & (b): Feature boxplots
    for idx, feature in enumerate(features):
        ax = fig.add_subplot(gs[0, idx])
        data = [df.loc[df["category"] == c, feature].dropna() for c in categories]
        
        bp = ax.boxplot(
            data, tick_labels=categories, patch_artist=True, widths=0.6,
            flierprops=dict(marker='o', markerfacecolor='gray', markersize=2, 
                          linestyle='none', alpha=0.5),
            boxprops=dict(facecolor=COLOR_PALETTE['box'], edgecolor='black', 
                         linewidth=0.8, alpha=0.7),
            medianprops=dict(color=COLOR_PALETTE['median'], linewidth=1.2),
            whiskerprops=dict(color='black', linewidth=0.8),
            capprops=dict(color='black', linewidth=0.8)
        )
        
        ax.set_xlabel('eGFR Categories (mL/min/1.73m²)', fontsize=9)
        ax.set_ylabel(feature_labels[feature], fontsize=9)
        ax.set_title(f'({chr(97+idx)}) {feature_labels[feature]}', 
                    loc='left', fontweight='bold', fontsize=10)
        ax.yaxis.grid(True, linestyle='--', alpha=0.3)
        ax.set_axisbelow(True)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(labelsize=8)
    
    # (c): Age distribution
    ax = fig.add_subplot(gs[1, :])
    age_data = [df.loc[df["category"] == c, "age"].dropna() for c in categories]
    
    bp = ax.boxplot(
        age_data, tick_labels=categories, patch_artist=True, widths=0.6,
        flierprops=dict(marker='o', markerfacecolor='gray', markersize=2, 
                       linestyle='none', alpha=0.5),
        boxprops=dict(facecolor=COLOR_PALETTE['box'], edgecolor='black', 
                     linewidth=0.8, alpha=0.7),
        medianprops=dict(color=COLOR_PALETTE['median'], linewidth=1.2),
        whiskerprops=dict(color='black', linewidth=0.8),
        capprops=dict(color='black', linewidth=0.8)
    )
    
    ax.set_xlabel('eGFR Categories (mL/min/1.73m²)', fontsize=9)
    ax.set_ylabel('Age (years)', fontsize=9)
    ax.set_title('(c) Age Distribution', loc='left', fontweight='bold', fontsize=10)
    ax.yaxis.grid(True, linestyle='--', alpha=0.3)
    ax.set_axisbelow(True)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(labelsize=8)
    
    # (d): Gender distribution
    ax = fig.add_subplot(gs[2, :])
    gender_counts = df.groupby(["category", "gender"]).size().unstack(fill_value=0)
    gender_counts = gender_counts.reindex(categories)
    
    for g in ["男", "女"]:
        if g not in gender_counts.columns:
            gender_counts[g] = 0
    
    x = np.arange(len(categories))
    width = 0.35
    
    ax.bar(x - width/2, gender_counts["男"], width, label='Male', 
           color=COLOR_PALETTE['male'], edgecolor='black', linewidth=0.8, alpha=0.8)
    ax.bar(x + width/2, gender_counts["女"], width, label='Female', 
           color=COLOR_PALETTE['female'], edgecolor='black', linewidth=0.8, alpha=0.8)
    
    ax.set_xlabel('eGFR Categories (mL/min/1.73m²)', fontsize=9)
    ax.set_ylabel('Number of Subjects', fontsize=9)
    ax.set_title('(d) Gender Distribution', loc='left', fontweight='bold', fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.legend(frameon=True, edgecolor='black', fancybox=False, fontsize=9)
    ax.yaxis.grid(True, linestyle='--', alpha=0.3)
    ax.set_axisbelow(True)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.set_ylim(bottom=0)
    ax.tick_params(labelsize=8)
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Combined figure saved: {output_path}")
    plt.show()

# ========================================
# Main Execution
# ========================================
if __name__ == "__main__":
    print("Generating publication-quality figures...")
    print("=" * 50)
    
    # Generate individual figures (each in separate window)
    print("\nGenerating feature boxplots (separate windows)...")
    plot_feature_boxplots(df, categories, 'figure1_features.png')
    
    print("\nGenerating age distribution...")
    plot_age_distribution(df, categories, 'figure2_age.png')
    
    print("\nGenerating gender distribution...")
    plot_gender_distribution(df, categories, 'figure3_gender.png')
    
    # Generate combined figure
    print("\nGenerating combined figure...")
    plot_combined_figure(df, categories, 'figure_combined.png')
    
    print("=" * 50)
    print("All figures generated successfully!")
    print("\nGenerated files:")
    print("  - figure1_features_Length_px.png (Length distribution)")
    print("  - figure1_features_Contrast_Ratio.png (Contrast ratio distribution)")
    print("  - figure2_age.png (Age distribution)")
    print("  - figure3_gender.png (Gender distribution)")
    print("  - figure_combined.png (All plots combined)")
    print("\nAll figures are saved at 300 DPI for publication quality.")
    print("Each plot is displayed in a separate window.")
