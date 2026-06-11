"""Cryo Chamber colour theme: frost-blue backgrounds, navy-blue borders."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

FROST_BG = "#E6F2FB"     # icy frost-blue window/panel background
FROST_PANEL = "#F2F9FE"  # slightly lighter panel fill
NAVY = "#16294D"         # deep navy for borders, text, accents
WHITE = "#FFFFFF"
BTN = "#CFE6F5"          # frosted button face
BTN_ACTIVE = "#AFD6EF"   # button hover/press
SELECT = "#2E6CA8"       # selection highlight (navy-leaning blue)


def apply_theme(root: tk.Misc) -> ttk.Style:
    """Apply the frost/navy theme to a Tk root and return the Style object."""
    try:
        root.configure(bg=FROST_BG)
    except tk.TclError:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")  # 'clam' lets us recolour borders
    except tk.TclError:
        pass

    style.configure(".", background=FROST_BG, foreground=NAVY,
                    bordercolor=NAVY, fieldbackground=WHITE, focuscolor=NAVY)
    style.configure("TFrame", background=FROST_BG)
    style.configure("TLabel", background=FROST_BG, foreground=NAVY)
    style.configure("TLabelframe", background=FROST_BG, bordercolor=NAVY,
                    relief="solid", borderwidth=2)
    style.configure("TLabelframe.Label", background=FROST_BG, foreground=NAVY,
                    font=("Segoe UI", 9, "bold"))

    style.configure("TButton", background=BTN, foreground=NAVY,
                    bordercolor=NAVY, borderwidth=1, focusthickness=1,
                    focuscolor=NAVY, padding=4)
    style.map("TButton",
              background=[("active", BTN_ACTIVE), ("pressed", BTN_ACTIVE)],
              bordercolor=[("focus", NAVY)])

    style.configure("TCheckbutton", background=FROST_BG, foreground=NAVY)
    style.map("TCheckbutton", background=[("active", FROST_BG)])

    for cls in ("TEntry", "TSpinbox", "TCombobox"):
        style.configure(cls, fieldbackground=WHITE, foreground=NAVY,
                        bordercolor=NAVY, borderwidth=1, arrowcolor=NAVY)
    style.map("TCombobox", fieldbackground=[("readonly", WHITE)])

    style.configure("TScale", background=FROST_BG, troughcolor=BTN)

    style.configure("TNotebook", background=FROST_BG, bordercolor=NAVY)
    style.configure("TNotebook.Tab", background=BTN, foreground=NAVY,
                    bordercolor=NAVY, padding=(12, 5))
    style.map("TNotebook.Tab",
              background=[("selected", FROST_PANEL)],
              foreground=[("selected", NAVY)])

    style.configure("Treeview", background=WHITE, fieldbackground=WHITE,
                    foreground=NAVY, bordercolor=NAVY)
    style.configure("Treeview.Heading", background=BTN, foreground=NAVY,
                    relief="flat")
    style.map("Treeview", background=[("selected", SELECT)],
              foreground=[("selected", WHITE)])

    style.configure("TScrollbar", background=BTN, bordercolor=NAVY,
                    arrowcolor=NAVY, troughcolor=FROST_BG)
    return style


def style_listbox(listbox: tk.Listbox) -> None:
    """Apply the theme to a classic tk.Listbox (not a ttk widget)."""
    listbox.configure(
        bg=WHITE, fg=NAVY,
        selectbackground=SELECT, selectforeground=WHITE,
        highlightthickness=1, highlightbackground=NAVY, highlightcolor=NAVY,
        borderwidth=1, relief="solid",
    )


def style_text(text: tk.Text) -> None:
    """Apply the theme to a classic tk.Text widget."""
    text.configure(
        bg=WHITE, fg=NAVY, insertbackground=NAVY,
        highlightthickness=1, highlightbackground=NAVY, highlightcolor=NAVY,
        borderwidth=1, relief="solid",
    )
