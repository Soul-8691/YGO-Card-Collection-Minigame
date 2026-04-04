from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from PIL import Image, ImageTk

from game_state import GameState

import random
import shutil

# Try to import pygame (for animations)
try:
    import pygame
except ImportError:
    pygame = None


# =========================
# Image path helper
# =========================

def _card_image_path(game_state: GameState, card_name: str) -> Path | None:
    """Return the path to cards/images_resized/{id}.jpg for a card, or None."""
    card_id = game_state.cardinfo_name_to_id.get(card_name)
    if card_id is None:
        return None
    path = game_state.base_path.parent / "cards" / "images_resized" / f"{card_id}.jpg"
    return path if path.exists() else None


# =========================
# Pygame pack-opening animation
# =========================

def play_pack_open_animation(game_state: GameState, card_names: list[str]) -> None:
    """
    Use pygame to animate card images "flying in" from the right.
    - Card images are 100x100 (from cards/images_resized/).
    - Card name is rendered below each image.
    - If sounds/pack_open.wav exists, play it once.
    - This function blocks until the animation finishes.
    """
    if pygame is None:
        # pygame not installed; silently skip
        return

    if not card_names:
        return

    # Card display size (cropped art, no resize)
    card_w, card_h = 100, 100
    spacing = 24
    margin = 20
    num = len(card_names)

    pygame.init()
    pygame.display.set_caption("Pack Opening")

    font = pygame.font.SysFont(None, 16)
    line_h = font.get_linesize()

    def wrap_text(text: str, max_w: int) -> list[str]:
        """Word-wrap text to fit within max_w pixels."""
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if font.size(test)[0] <= max_w:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [text]

    # Pre-compute wrapped name lines for each card so we know max line count.
    wrapped_names: list[list[str]] = [wrap_text(n, card_w) for n in card_names]
    max_name_lines = max(len(w) for w in wrapped_names)
    name_area_h = max_name_lines * line_h + 4
    slot_h = card_h + name_area_h

    # Compute window size
    window_w = margin * 2 + num * card_w + (num - 1) * spacing
    window_h = slot_h + margin * 2

    screen = pygame.display.set_mode((window_w, window_h))

    # Load card images
    card_surfaces: list[pygame.Surface] = []

    for name in card_names:
        path = _card_image_path(game_state, name)
        if path is not None:
            try:
                img = pygame.image.load(path.as_posix()).convert_alpha()
                surf = pygame.transform.smoothscale(img, (card_w, card_h))
            except Exception:
                surf = pygame.Surface((card_w, card_h))
                surf.fill((80, 80, 80))
        else:
            surf = pygame.Surface((card_w, card_h))
            surf.fill((80, 80, 80))

        card_surfaces.append(surf)

    # Optional sound
    sound_path = game_state.base_path.parent / "sounds" / "pack_open.wav"
    if sound_path.exists():
        try:
            pygame.mixer.init()
            sound = pygame.mixer.Sound(sound_path.as_posix())
            sound.play()
        except Exception:
            pass

    clock = pygame.time.Clock()
    duration_ms = 1000  # animation duration ~1s
    start_time = pygame.time.get_ticks()

    running = True
    while running:
        now = pygame.time.get_ticks()
        t = (now - start_time) / duration_ms
        if t >= 1.0:
            t = 1.0
            running = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

        screen.fill((20, 20, 40))

        for i, (surf, lines) in enumerate(zip(card_surfaces, wrapped_names)):
            target_x = margin + i * (card_w + spacing)
            y = margin
            start_x = window_w
            x = start_x + (target_x - start_x) * t
            screen.blit(surf, (x, y))

            # Render wrapped card name lines below the image, clipped to card width.
            ny = y + card_h + 4
            for line in lines:
                name_surf = font.render(line, True, (220, 220, 220))
                nx = x + (card_w - name_surf.get_width()) / 2
                screen.blit(name_surf, (nx, ny))
                ny += line_h

        pygame.display.flip()
        clock.tick(60)

    # Leave cards on screen for ~3.5 seconds, still processing events so the
    # window stays responsive (and the user can close it early with the X button).
    hold_ms = 3500
    hold_start = pygame.time.get_ticks()
    while pygame.time.get_ticks() - hold_start < hold_ms:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
        clock.tick(30)
    pygame.quit()


# =========================
# Shop Tab
# =========================

class ShopFrame(ttk.Frame):
    def __init__(
        self,
        parent,
        game_state: GameState,
        participant_var: tk.StringVar,
        on_after_reset=None,
        on_after_pack_open=None,
    ):
        super().__init__(parent)

        self.game_state = game_state
        self.participant_var = participant_var
        self.on_after_reset = on_after_reset
        self.on_after_pack_open = on_after_pack_open

        # Keep track of the names in the listboxes
        self.pack_names: list[str] = []          # all packs, sorted
        self.filtered_pack_names: list[str] = [] # visible after search filter
        self.card_names: list[str] = []

        # Card preview image reference (avoid GC)
        self.card_image_tk = None

        # ----- Layout -----
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        # Top: participant + DP + reset
        top_frame = ttk.Frame(self)
        top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        top_frame.columnconfigure(2, weight=1)

        ttk.Label(top_frame, text="Participant:").grid(row=0, column=0, sticky="w")
        self.participant_combo = ttk.Combobox(
            top_frame,
            textvariable=self.participant_var,
            values=list(self.game_state.participants.keys()),
            state="readonly",
            width=20,
        )
        self.participant_combo.grid(row=0, column=1, sticky="w")

        self.dp_label_var = tk.StringVar(value="DP: 0")
        self.dp_label = ttk.Label(top_frame, textvariable=self.dp_label_var)
        self.dp_label.grid(row=0, column=2, sticky="e", padx=(0, 8))

        self.reset_button = ttk.Button(
            top_frame, text="Reset Participant", command=self.on_reset_participant
        )
        self.reset_button.grid(row=0, column=3, sticky="e")

        # Left side: packs
        packs_frame = ttk.LabelFrame(self, text="Packs")
        packs_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        packs_frame.rowconfigure(2, weight=1)
        packs_frame.columnconfigure(0, weight=1)

        # Pack search bar
        pack_search_frame = ttk.Frame(packs_frame)
        pack_search_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=2, pady=(4, 2))
        pack_search_frame.columnconfigure(1, weight=1)
        ttk.Label(pack_search_frame, text="Search:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.pack_search_var = tk.StringVar()
        self.pack_search_var.trace_add("write", lambda *_: self._filter_packs())
        pack_search_entry = ttk.Entry(pack_search_frame, textvariable=self.pack_search_var)
        pack_search_entry.grid(row=0, column=1, sticky="ew")

        self.packs_listbox = tk.Listbox(packs_frame, height=12)
        self.packs_listbox.grid(row=2, column=0, sticky="nsew")

        packs_scroll = ttk.Scrollbar(
            packs_frame, orient="vertical", command=self.packs_listbox.yview
        )
        packs_scroll.grid(row=2, column=1, sticky="ns")
        self.packs_listbox.configure(yscrollcommand=packs_scroll.set)

        # Pack buttons
        pack_btn_frame = ttk.Frame(packs_frame)
        pack_btn_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        pack_btn_frame.columnconfigure(0, weight=1)
        pack_btn_frame.columnconfigure(1, weight=1)

        self.btn_unlock_pack = ttk.Button(
            pack_btn_frame, text="Unlock Pack", command=self.on_unlock_pack
        )
        self.btn_unlock_pack.grid(row=0, column=0, sticky="ew", padx=2)

        self.btn_buy_pack = ttk.Button(
            pack_btn_frame, text="Buy & Open Pack", command=self.on_buy_pack
        )
        self.btn_buy_pack.grid(row=0, column=1, sticky="ew", padx=2)

        # Right side: cards + preview
        cards_frame = ttk.LabelFrame(self, text="Cards")
        cards_frame.grid(row=1, column=1, sticky="nsew", padx=8, pady=8)

        cards_frame.rowconfigure(1, weight=1)
        cards_frame.columnconfigure(0, weight=3)  # list
        cards_frame.columnconfigure(2, weight=2)  # preview

        # Card list
        self.cards_listbox = tk.Listbox(cards_frame, height=12)
        self.cards_listbox.grid(row=1, column=0, sticky="nsew")

        self.packs_listbox.bind("<Double-Button-1>", self.on_pack_double_click)
        self.cards_listbox.bind("<Double-Button-1>", self.on_card_double_click)

        cards_scroll = ttk.Scrollbar(
            cards_frame, orient="vertical", command=self.cards_listbox.yview
        )
        cards_scroll.grid(row=1, column=1, sticky="ns")
        self.cards_listbox.configure(yscrollcommand=cards_scroll.set)

        # Card preview
        self.preview_label = ttk.Label(cards_frame, text="(No card selected)")
        self.preview_label.grid(row=1, column=2, sticky="n", padx=8, pady=8)

        # Card buttons
        card_btn_frame = ttk.Frame(cards_frame)
        card_btn_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        card_btn_frame.columnconfigure(0, weight=1)
        card_btn_frame.columnconfigure(1, weight=1)

        self.btn_unlock_card = ttk.Button(
            card_btn_frame, text="Unlock Card", command=self.on_unlock_card
        )
        self.btn_unlock_card.grid(row=0, column=0, sticky="ew", padx=2)

        self.btn_buy_card = ttk.Button(
            card_btn_frame, text="Buy Card Copy", command=self.on_buy_card_copy
        )
        self.btn_buy_card.grid(row=0, column=1, sticky="ew", padx=2)

        # Refresh when participant changes
        self.participant_combo.bind("<<ComboboxSelected>>", self.on_participant_changed)

        # When a card is selected, update preview
        self.cards_listbox.bind("<<ListboxSelect>>", self.on_card_selected)

        # Initial fill
        self.refresh_view()

    # ---- Utility methods ----

    # ---- Info popups for unlock requirements ----

    def on_pack_double_click(self, event=None):
        pack_name = self._get_selected_pack_name()
        if pack_name is None:
            return
        self.show_pack_info(pack_name)

    def on_card_double_click(self, event=None):
        card_name = self._get_selected_card_name()
        if card_name is None:
            return
        self.show_card_info(card_name)

    def show_pack_info(self, pack_name: str):
        participant_name = self.participant_var.get()
        participant = self.get_current_participant()
        pack_def = self.game_state.packs.get(pack_name)
        if not pack_def:
            messagebox.showinfo("Pack Info", f"Unknown pack: {pack_name}")
            return

        display_name = pack_def.get("display_name", pack_name)
        unlock_cost = pack_def.get("unlock_cost", 0)
        pack_cost = pack_def.get("pack_cost", 0)
        requirements = pack_def.get("unlock_requirements", {})
        unlocked_packs = set(participant.get("unlocked_packs", []))

        lines = []
        lines.append(f"Internal name: {pack_name}")
        lines.append(f"Display name: {display_name}")
        lines.append(f"Unlock cost: {unlock_cost} DP")
        lines.append(f"Pack cost: {pack_cost} DP")
        lines.append("")

        if pack_name in unlocked_packs:
            lines.append("Status: Already unlocked.")
        else:
            lines.append("Status: Locked.")
            ok, reason = self.game_state.can_unlock_pack(participant_name, pack_name)
            lines.append(f"Can unlock now? {'Yes' if ok else 'No'}")
            lines.append(f"Reason: {reason}")
        lines.append("")

        if not requirements:
            lines.append("Unlock requirements:")
            lines.append("  None (just pay unlock cost).")
        else:
            lines.append("Unlock requirements:")
            tier_min = requirements.get("tier_min")
            if tier_min is not None:
                current_tier = participant.get("tier", 1)
                lines.append(f"  Tier at least {tier_min} (you are Tier {current_tier})")

            beat_req = requirements.get("beat_duelist_counts", {})
            if beat_req:
                lines.append("  Duelist wins needed:")
                beat_counts = participant.get("beat_counts", {})
                for duelist_name, needed in beat_req.items():
                    have = beat_counts.get(duelist_name, 0)
                    remaining = max(0, needed - have)
                    lines.append(
                        f"    {duelist_name}: {needed} wins "
                        f"(you have {have}, need {remaining} more)"
                    )

        messagebox.showinfo(f"Pack Info: {display_name}", "\n".join(lines))

    def show_card_info(self, card_name: str):
        participant_name = self.participant_var.get()
        participant = self.get_current_participant()
        card_def = self.game_state.cards.get(card_name)
        if not card_def:
            messagebox.showinfo("Card Info", f"Unknown card: {card_name}")
            return

        price = card_def.get("price")
        unlock_cost = card_def.get("unlock_cost")
        max_copies = card_def.get("max_copies", 3)
        owned = participant.get("card_collection", {}).get(card_name, 0)
        unlocked_cards = set(participant.get("unlocked_cards", []))
        requirements = card_def.get("unlock_requirements", {})

        lines = []
        lines.append(f"Name: {card_name}")
        lines.append(f"Owned: {owned}/{max_copies}")
        if price is not None:
            lines.append(f"Price per copy: {price} DP")
        else:
            lines.append("Price per copy: Not purchasable")

        if unlock_cost is not None:
            lines.append(f"Unlock cost: {unlock_cost} DP")
        else:
            lines.append("Unlock cost: None (no unlock step; buy directly if purchasable)")

        lines.append("")

        # Status and can_unlock info
        if unlock_cost is not None:
            if card_name in unlocked_cards:
                lines.append("Unlock status: Already unlocked.")
            else:
                lines.append("Unlock status: Locked.")
                ok, reason = self.game_state.can_unlock_card(participant_name, card_name)
                lines.append(f"Can unlock now? {'Yes' if ok else 'No'}")
                lines.append(f"Reason: {reason}")
        else:
            lines.append("Unlock status: No unlock needed.")

        lines.append("")

        # Requirements details
        if not requirements:
            if unlock_cost is not None:
                lines.append("Unlock requirements:")
                lines.append("  None (just pay unlock cost).")
            else:
                lines.append("Unlock requirements:")
                lines.append("  None.")
        else:
            lines.append("Unlock requirements:")
            tier_min = requirements.get("tier_min")
            if tier_min is not None:
                current_tier = participant.get("tier", 1)
                lines.append(f"  Tier at least {tier_min} (you are Tier {current_tier})")

            beat_req = requirements.get("beat_duelist_counts", {})
            if beat_req:
                lines.append("  Duelist wins needed:")
                beat_counts = participant.get("beat_counts", {})
                for duelist_name, needed in beat_req.items():
                    have = beat_counts.get(duelist_name, 0)
                    remaining = max(0, needed - have)
                    lines.append(
                        f"    {duelist_name}: {needed} wins "
                        f"(you have {have}, need {remaining} more)"
                    )

        messagebox.showinfo(f"Card Info: {card_name}", "\n".join(lines))

    def get_current_participant(self) -> dict:
        name = self.participant_var.get()
        if not name:
            raise RuntimeError("No participant selected.")
        p = self.game_state.get_participant(name)
        self.game_state._ensure_participant_struct(p)
        return p

    def refresh_view(self) -> None:
        try:
            participant = self.get_current_participant()
        except Exception:
            self.dp_label_var.set("DP: -")
            return

        # DP label
        self.dp_label_var.set(f"DP: {participant.get('dp', 0)}")

        # Packs — build full list then apply current search filter
        self.pack_names = sorted(self.game_state.packs.keys())
        self._filter_packs()

        # Cards
        self.card_names = sorted(self.game_state.cards.keys())
        self.cards_listbox.delete(0, tk.END)

        unlocked_cards = set(participant.get("unlocked_cards", []))
        collection = participant.get("card_collection", {})

        for card_name in self.card_names:
            card_def = self.game_state.cards[card_name]
            price = card_def.get("price")
            unlock_cost = card_def.get("unlock_cost")
            max_copies = card_def.get("max_copies", 3)
            owned = collection.get(card_name, 0)

            if unlock_cost is not None:
                if card_name in unlocked_cards:
                    status = "[Unlocked]"
                else:
                    status = "[Locked]"
            else:
                status = "[No unlock needed]"

            price_str = f"{price} DP/copy" if price is not None else "Not for sale"
            unlock_str = f"Unlock: {unlock_cost} DP" if unlock_cost is not None else ""
            text = (
                f"{card_name} {status}  "
                f"[Owned: {owned}/{max_copies}]  {price_str} {unlock_str}"
            )
            self.cards_listbox.insert(tk.END, text)

        # Clear preview if list changed
        self.card_image_tk = None
        self.preview_label.config(text="(No card selected)", image="")

    def _filter_packs(self) -> None:
        """Re-populate the packs listbox using the current search term."""
        query = self.pack_search_var.get().lower()
        try:
            participant = self.get_current_participant()
        except Exception:
            return
        unlocked_packs = set(participant.get("unlocked_packs", []))

        self.filtered_pack_names = [
            p for p in self.pack_names
            if query in p.lower()
            or query in self.game_state.packs[p].get("display_name", "").lower()
        ]

        self.packs_listbox.delete(0, tk.END)
        for pack_name in self.filtered_pack_names:
            pack_def = self.game_state.packs[pack_name]
            display_name = pack_def.get("display_name", pack_name)
            unlock_cost = pack_def.get("unlock_cost", 0)
            pack_cost = pack_def.get("pack_cost", 0)
            status = "[Unlocked]" if pack_name in unlocked_packs else "[Locked]"
            text = f"{display_name} {status}  (Unlock: {unlock_cost} DP, Pack: {pack_cost} DP)"
            self.packs_listbox.insert(tk.END, text)

    def _get_selected_pack_name(self) -> str | None:
        sel = self.packs_listbox.curselection()
        if not sel:
            return None
        index = sel[0]
        if 0 <= index < len(self.filtered_pack_names):
            return self.filtered_pack_names[index]
        return None

    def _get_selected_card_name(self) -> str | None:
        sel = self.cards_listbox.curselection()
        if not sel:
            return None
        index = sel[0]
        if 0 <= index < len(self.card_names):
            return self.card_names[index]
        return None

    def show_selected_card_image(self, card_name: str) -> None:
        path = _card_image_path(self.game_state, card_name)

        if path is None:
            self.preview_label.config(text="(Image not found)", image="")
            self.card_image_tk = None
            return

        try:
            img = Image.open(path)
            max_w, max_h = 200, 200
            img.thumbnail((max_w, max_h), Image.LANCZOS)
            self.card_image_tk = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self.card_image_tk, text="")
        except Exception as e:
            self.preview_label.config(text=f"(Error loading image)\n{e}", image="")
            self.card_image_tk = None

    # ---- Event handlers ----

    def on_participant_changed(self, event=None):
        self.refresh_view()

    def on_card_selected(self, event=None):
        card_name = self._get_selected_card_name()
        if card_name:
            self.show_selected_card_image(card_name)

    def on_reset_participant(self):
        name = self.participant_var.get()
        if not name:
            messagebox.showwarning("Reset Participant", "No participant selected.")
            return

        if not messagebox.askyesno(
            "Reset Participant",
            f"Are you sure you want to reset '{name}'?\n"
            "This will clear DP, tier, packs, cards, and duel history.",
        ):
            return

        self.game_state.reset_participant(name)
        messagebox.showinfo("Reset Complete", f"Participant '{name}' has been reset.")
        self.refresh_view()

        if self.on_after_reset:
            self.on_after_reset()

    # ---- Pack actions ----

    def on_unlock_pack(self):
        pack_name = self._get_selected_pack_name()
        if pack_name is None:
            messagebox.showinfo("Unlock Pack", "Please select a pack first.")
            return

        participant_name = self.participant_var.get()
        ok, reason = self.game_state.can_unlock_pack(participant_name, pack_name)
        if not ok:
            messagebox.showwarning("Cannot Unlock Pack", reason)
            return

        if not messagebox.askyesno(
            "Confirm Unlock",
            f"Unlock pack '{pack_name}'?\n\n{reason}",
        ):
            return

        success = self.game_state.unlock_pack(participant_name, pack_name)
        if success:
            messagebox.showinfo("Pack Unlocked", f"Pack '{pack_name}' unlocked!")
        self.refresh_view()

    def on_buy_pack(self):
        pack_name = self._get_selected_pack_name()
        if pack_name is None:
            messagebox.showinfo("Buy Pack", "Please select a pack first.")
            return

        participant_name = self.participant_var.get()
        ok, reason = self.game_state.can_buy_pack(participant_name, pack_name)
        if not ok:
            messagebox.showwarning("Cannot Buy Pack", reason)
            return

        try:
            pulled = self.game_state.open_pack_for_participant(
                participant_name, pack_name, pay_with_dp=True, require_unlocked=True
            )
        except Exception as e:
            messagebox.showerror("Error Opening Pack", str(e))
            return

        # Pygame animation
        play_pack_open_animation(self.game_state, pulled)

        pulled_str = "\n".join(pulled) if pulled else "(No cards pulled?)"
        messagebox.showinfo("Pack Opened", f"You pulled:\n\n{pulled_str}")
        self.refresh_view()
        if self.on_after_pack_open:
            self.on_after_pack_open()

    # ---- Card actions ----

    def on_unlock_card(self):
        card_name = self._get_selected_card_name()
        if card_name is None:
            messagebox.showinfo("Unlock Card", "Please select a card first.")
            return

        participant_name = self.participant_var.get()
        ok, reason = self.game_state.can_unlock_card(participant_name, card_name)
        if not ok:
            messagebox.showwarning("Cannot Unlock Card", reason)
            return

        if not messagebox.askyesno(
            "Confirm Unlock",
            f"Unlock card '{card_name}'?\n\n{reason}",
        ):
            return

        success = self.game_state.unlock_card(participant_name, card_name)
        if success:
            messagebox.showinfo("Card Unlocked", f"Card '{card_name}' unlocked!")
        self.refresh_view()

    def on_buy_card_copy(self):
        card_name = self._get_selected_card_name()
        if card_name is None:
            messagebox.showinfo("Buy Card Copy", "Please select a card first.")
            return

        participant_name = self.participant_var.get()
        ok, reason = self.game_state.can_buy_card_copy(participant_name, card_name)
        if not ok:
            messagebox.showwarning("Cannot Buy Card Copy", reason)
            return

        success = self.game_state.buy_card_copy(participant_name, card_name)
        if success:
            messagebox.showinfo("Card Purchased", f"Bought one copy of '{card_name}'.")
        self.refresh_view()


# =========================
# Duel Log Tab
# =========================

class DuelLogFrame(ttk.Frame):
    def __init__(
        self,
        parent,
        game_state: GameState,
        participant_var: tk.StringVar,
        on_after_duel=None,
    ):
        super().__init__(parent)

        self.game_state = game_state
        self.participant_var = participant_var
        self.on_after_duel = on_after_duel

        self.opponent_var = tk.StringVar()
        self.role_var = tk.StringVar(value="participant")
        self.result_var = tk.StringVar(value="win")

        # Deck export settings (per-session)
        self.deck_export_dir: Path | None = None
        self.deck_export_auto: bool = False

        # Layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Top row: participant + Tier + DP
        top_frame = ttk.Frame(self)
        top_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        top_frame.columnconfigure(4, weight=1)

        ttk.Label(top_frame, text="Participant:").grid(row=0, column=0, sticky="w")
        self.participant_combo = ttk.Combobox(
            top_frame,
            textvariable=self.participant_var,
            values=list(self.game_state.participants.keys()),
            state="readonly",
            width=20,
        )
        self.participant_combo.grid(row=0, column=1, sticky="w")

        self.tier_label_var = tk.StringVar(value="Tier: 1")
        ttk.Label(top_frame, textvariable=self.tier_label_var).grid(
            row=0, column=2, sticky="e", padx=(16, 8)
        )

        self.dp_label_var = tk.StringVar(value="DP: 0")
        ttk.Label(top_frame, textvariable=self.dp_label_var).grid(
            row=0, column=3, sticky="e"
        )

        # Middle: duel input
        mid_frame = ttk.LabelFrame(self, text="Record Duel")
        mid_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        # Opponent
        ttk.Label(mid_frame, text="Opponent:").grid(row=0, column=0, sticky="w", padx=4, pady=2)

        opponent_names = list(self.game_state.duelists.keys())
        self.opponent_combo = ttk.Combobox(
            mid_frame,
            textvariable=self.opponent_var,
            values=opponent_names,
            state="normal",
            width=25,
        )
        self.opponent_combo.grid(row=0, column=1, sticky="w", padx=4, pady=2)

        # Roll for opponent deck
        self.roll_deck_button = ttk.Button(
            mid_frame, text="Roll deck", command=self.on_roll_deck
        )
        self.roll_deck_button.grid(row=0, column=2, sticky="w", padx=4, pady=2)

        # NEW: Manage deck directory / auto-copy settings
        self.manage_deck_dir_button = ttk.Button(
            mid_frame, text="Manage EDOPro deck directory", command=self.on_manage_deck_dir
        )
        self.manage_deck_dir_button.grid(row=0, column=3, sticky="w", padx=4, pady=2)

        # Role
        ttk.Label(mid_frame, text="Role:").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        role_frame = ttk.Frame(mid_frame)
        role_frame.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Radiobutton(
            role_frame, text="Participant", value="participant", variable=self.role_var
        ).pack(side="left")
        ttk.Radiobutton(
            role_frame, text="NPC", value="npc", variable=self.role_var
        ).pack(side="left")

        # Result
        ttk.Label(mid_frame, text="Result:").grid(row=2, column=0, sticky="w", padx=4, pady=2)
        result_frame = ttk.Frame(mid_frame)
        result_frame.grid(row=2, column=1, sticky="w", padx=4, pady=2)
        ttk.Radiobutton(
            result_frame, text="Win", value="win", variable=self.result_var
        ).pack(side="left")
        ttk.Radiobutton(
            result_frame, text="Loss", value="loss", variable=self.result_var
        ).pack(side="left")
        ttk.Radiobutton(
            result_frame, text="Draw", value="draw", variable=self.result_var
        ).pack(side="left")

        # Record button
        self.record_button = ttk.Button(
            mid_frame, text="Record Duel", command=self.on_record_duel
        )
        self.record_button.grid(row=3, column=0, columnspan=3, pady=6)

        # Bottom: recent duels
        bottom_frame = ttk.LabelFrame(self, text="Recent Duels")
        bottom_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)

        bottom_frame.rowconfigure(0, weight=1)
        bottom_frame.columnconfigure(0, weight=1)

        self.duel_listbox = tk.Listbox(bottom_frame, height=12)
        self.duel_listbox.grid(row=0, column=0, sticky="nsew")

        duel_scroll = ttk.Scrollbar(
            bottom_frame, orient="vertical", command=self.duel_listbox.yview
        )
        duel_scroll.grid(row=0, column=1, sticky="ns")
        self.duel_listbox.configure(yscrollcommand=duel_scroll.set)

        # Participant change refresh
        self.participant_combo.bind("<<ComboboxSelected>>", self.on_participant_changed)

        self.refresh_view()

    def on_manage_deck_dir(self):
        """
        Let the user view/change the EDOPro deck directory and auto-copy setting.
        This only affects this app session (not persisted yet).
        """
        current_dir = str(self.deck_export_dir) if self.deck_export_dir else "(not set)"
        auto_status = "ON" if self.deck_export_auto else "OFF"

        msg = (
            "Current EDOPro deck directory:\n"
            f"{current_dir}\n\n"
            f"Automatic copy of rolled decks: {auto_status}\n\n"
            "Choose an action:\n"
            "- 'Yes': Change directory and auto-copy setting.\n"
            "- 'No': Clear directory and disable auto-copy.\n"
            "- 'Cancel': Leave settings unchanged."
        )

        choice = messagebox.askyesnocancel(
            "Manage EDOPro deck directory", msg
        )
        # choice is True (Yes), False (No), or None (Cancel)

        if choice is None:
            # Cancel
            return

        if choice is False:
            # Clear settings
            self.deck_export_dir = None
            self.deck_export_auto = False
            messagebox.showinfo(
                "Deck Directory",
                "Deck export directory cleared and auto-copy disabled."
            )
            return

        # choice is True: change directory + auto-copy flag
        dirname = filedialog.askdirectory(
            title="Select EDOPro deck directory (where .ydk files go)"
        )
        if not dirname:
            return

        self.deck_export_dir = Path(dirname)

        # Ask for auto-copy preference
        auto = messagebox.askyesno(
            "Auto-Copy Rolled Decks?",
            "Enable automatic copying of rolled decks to this directory?\n\n"
            f"{self.deck_export_dir}"
        )
        self.deck_export_auto = bool(auto)

        messagebox.showinfo(
            "Deck Directory",
            "EDOPro deck directory updated.\n\n"
            f"Directory: {self.deck_export_dir}\n"
            f"Auto-copy: {'ON' if self.deck_export_auto else 'OFF'}",
        )

    def get_current_participant(self) -> dict:
        name = self.participant_var.get()
        if not name:
            raise RuntimeError("No participant selected.")
        p = self.game_state.get_participant(name)
        self.game_state._ensure_participant_struct(p)
        return p

    def refresh_view(self):
        try:
            participant = self.get_current_participant()
        except Exception:
            self.dp_label_var.set("DP: -")
            self.tier_label_var.set("Tier: -")
            self.duel_listbox.delete(0, tk.END)
            return

        self.dp_label_var.set(f"DP: {participant.get('dp', 0)}")
        self.tier_label_var.set(f"Tier: {participant.get('tier', 1)}")

        history = participant.get("duel_history", [])
        self.duel_listbox.delete(0, tk.END)

        for entry in reversed(history[-50:]):
            ts = entry.get("timestamp", "?")
            opp = entry.get("opponent", "?")
            role = entry.get("role", "?")
            result = entry.get("result", "?")
            dp_change = entry.get("dp_change", 0)
            free_pack = entry.get("free_pack")

            base_text = f"[{ts}] vs {opp} ({role}) - {result}"
            if dp_change:
                base_text += f", DP +{dp_change}"
            if free_pack:
                base_text += f", Free pack: {free_pack}"
            self.duel_listbox.insert(tk.END, base_text)

    def on_participant_changed(self, event=None):
        self.refresh_view()

    # ---- Deck roll & export helpers ----

    def _resolve_deck_path(self, deck_id: str | None) -> Path | None:
        """
        Try to resolve deck_id to an actual file path.
        Strategy:
          - If deck_id is an absolute or relative existing path, use it.
          - Else, try base_path.parent / deck_id
          - Else, try base_path.parent / "decks" / deck_id
        """
        if not deck_id:
            return None

        p = Path(deck_id)
        if p.exists():
            return p

        base_root = self.game_state.base_path.parent

        alt = base_root / deck_id
        if alt.exists():
            return alt

        alt2 = base_root / "decks" / deck_id
        if alt2.exists():
            return alt2

        return None

    def _copy_deck_to_clipboard(self, deck_path: Path | None, deck_id: str | None):
        """
        Copy deck information to the clipboard.

        Since we can't reliably put a real "file object" on the OS clipboard
        cross-platform, we copy something textual:
        - If we have a deck_path, copy that full path.
        - Otherwise, copy the deck_id.
        """
        text = None
        if deck_path is not None:
            text = str(deck_path)
        elif deck_id:
            text = str(deck_id)

        if text:
            try:
                self.clipboard_clear()
                self.clipboard_append(text)
                self.update()  # make sure clipboard is updated
            except Exception:
                pass

    def _maybe_copy_deck_file_to_edopro(self, deck_path: Path):
        """
        Optionally copy the deck file into an EDOPro deck directory.
        - If auto export is enabled & directory exists, copy directly.
        - Otherwise, ask the user if they want to copy, and (if yes)
          ask for the directory, and optionally enable auto export.
        """
        if not deck_path.exists():
            messagebox.showinfo(
                "Copy Deck",
                f"Deck file does not exist on disk:\n{deck_path}",
            )
            return

        # Auto export path known & enabled
        if self.deck_export_auto and self.deck_export_dir and self.deck_export_dir.exists():
            dest = self.deck_export_dir / deck_path.name
            try:
                shutil.copy2(deck_path, dest)
                messagebox.showinfo(
                    "Deck Copied",
                    f"Deck copied automatically to:\n{dest}",
                )
            except Exception as e:
                messagebox.showerror(
                    "Deck Copy Error",
                    f"Failed to copy deck to:\n{dest}\n\n{e}",
                )
            return

        # Otherwise, ask one-off
        if not messagebox.askyesno(
            "Copy Deck",
            "Copy this deck file into an EDOPro deck directory now?",
        ):
            return

        # Choose or reuse deck export directory
        if self.deck_export_dir is None or not self.deck_export_dir.exists():
            dirname = filedialog.askdirectory(
                title="Select EDOPro deck directory (where .ydk files go)"
            )
            if not dirname:
                return
            self.deck_export_dir = Path(dirname)

        dest = self.deck_export_dir / deck_path.name
        try:
            shutil.copy2(deck_path, dest)
        except Exception as e:
            messagebox.showerror(
                "Deck Copy Error",
                f"Failed to copy deck to:\n{dest}\n\n{e}",
            )
            return

        # Ask if we should always auto copy in this session
        if not self.deck_export_auto:
            if messagebox.askyesno(
                "Auto Copy Decks?",
                "Deck copied successfully.\n\n"
                "Always copy rolled decks to this directory automatically?\n\n"
                f"{self.deck_export_dir}",
            ):
                self.deck_export_auto = True

        messagebox.showinfo(
            "Deck Copied",
            f"Deck copied to:\n{dest}",
        )

    def on_roll_deck(self):
        duelist_name = self.opponent_var.get().strip()
        if not duelist_name:
            messagebox.showwarning("Roll Deck", "Please choose an opponent first.")
            return

        duelist_def = self.game_state.duelists.get(duelist_name)
        if not duelist_def:
            messagebox.showinfo(
                "Roll Deck", f"'{duelist_name}' is not defined as a duelist."
            )
            return

        teams = duelist_def.get("teams")
        if not isinstance(teams, dict) or not teams:
            messagebox.showinfo(
                "Roll Deck", f"No teams defined for {duelist_name}."
            )
            return

        names = []
        weights = []
        for team_name, team_def in teams.items():
            if isinstance(team_def, dict):
                w = team_def.get("weight", 1.0)
            else:
                w = 1.0
            try:
                w = float(w)
            except Exception:
                w = 1.0
            if w <= 0:
                continue
            names.append(team_name)
            weights.append(w)

        if not names:
            messagebox.showinfo(
                "Roll Deck", f"No valid weighted teams for {duelist_name}."
            )
            return

        chosen = random.choices(names, weights=weights, k=1)[0]
        team_def = teams.get(chosen, {})
        deck_id = None
        if isinstance(team_def, dict):
            deck_id = (
                team_def.get("deck_file")
            )

        deck_path = self._resolve_deck_path(deck_id)
        self._copy_deck_to_clipboard(deck_path, deck_id)

        msg = f"{duelist_name} will use deck:\n\n{chosen}"
        if deck_id:
            msg += f"\n\nDeck ID / file:\n{deck_id}"
        if deck_path:
            msg += f"\n\nResolved path:\n{deck_path}\n\n"
            msg += "The deck path has been copied to the clipboard."
        else:
            msg += "\n\nThe deck ID has been copied to the clipboard."

        messagebox.showinfo("Rolled Deck", msg)

        # Offer to copy the file into EDOPro deck directory if we have a path
        if deck_path is not None:
            self._maybe_copy_deck_file_to_edopro(deck_path)

    # ---- Record duel ----

    def on_record_duel(self):
        participant_name = self.participant_var.get()
        if not participant_name:
            messagebox.showwarning("Record Duel", "No participant selected.")
            return

        opponent_name = self.opponent_var.get().strip()
        if not opponent_name:
            messagebox.showwarning("Record Duel", "Please enter an opponent name.")
            return

        result = self.result_var.get()
        role = self.role_var.get()

        try:
            info = self.game_state.record_duel(
                participant_name, opponent_name, result, role
            )
        except Exception as e:
            messagebox.showerror("Error Recording Duel", str(e))
            return

        dp_change = info.get("dp_change", 0)
        free_pack = info.get("free_pack")

        msg = f"Recorded {result} vs {opponent_name} as {role}."
        if dp_change:
            msg += f"\nDP gained: {dp_change}"

        pulled_str = None
        if result == "win" and free_pack:
            try:
                pulled = self.game_state.open_pack_for_participant(
                    participant_name,
                    free_pack,
                    pay_with_dp=False,
                    require_unlocked=False,
                )
                # Pygame animation for free pack
                play_pack_open_animation(self.game_state, pulled)

                pulled_str = "\n".join(pulled) if pulled else "(No cards pulled?)"
            except Exception as e:
                messagebox.showerror("Error Opening Reward Pack", str(e))
            else:
                msg += f"\n\nFree pack opened: {free_pack}"

        messagebox.showinfo("Duel Recorded", msg)

        if pulled_str:
            messagebox.showinfo(
                "Free Pack Result",
                f"You pulled from {free_pack}:\n\n{pulled_str}",
            )

        self.refresh_view()
        if self.on_after_duel:
            self.on_after_duel()


# =========================
# Collection Tab
# =========================

class CollectionFrame(ttk.Frame):
    def __init__(
        self,
        parent,
        game_state: GameState,
        participant_var: tk.StringVar,
    ):
        super().__init__(parent)

        self.game_state = game_state
        self.participant_var = participant_var

        # Keep references to card images (for gallery) to avoid GC
        self.card_images_gallery: dict[str, ImageTk.PhotoImage] = {}

        # Whether to show full card art gallery
        self.show_art_var = tk.BooleanVar(value=False)

        # Search/filter string
        self.search_var = tk.StringVar(value="")

        # Filter by owned count: All / 1 / 2 / 3+
        self.owned_filter_var = tk.StringVar(value="All")

        # Sort mode: Name / Owned (desc)
        self.sort_var = tk.StringVar(value="Name")

        # Layout: 3 rows
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        # ---- Top: participant + DP + Tier + export + toggle + search + sort/filter ----
        top_frame = ttk.Frame(self)
        top_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        for i in range(8):
            top_frame.columnconfigure(i, weight=0)
        top_frame.columnconfigure(7, weight=1)  # spacer

        ttk.Label(top_frame, text="Participant:").grid(row=0, column=0, sticky="w")
        self.participant_combo = ttk.Combobox(
            top_frame,
            textvariable=self.participant_var,
            values=list(self.game_state.participants.keys()),
            state="readonly",
            width=20,
        )
        self.participant_combo.grid(row=0, column=1, sticky="w")

        self.tier_label_var = tk.StringVar(value="Tier: 1")
        ttk.Label(top_frame, textvariable=self.tier_label_var).grid(
            row=0, column=2, sticky="e", padx=(16, 8)
        )

        self.dp_label_var = tk.StringVar(value="DP: 0")
        ttk.Label(top_frame, textvariable=self.dp_label_var).grid(
            row=0, column=3, sticky="e"
        )

        # Export buttons
        export_txt_btn = ttk.Button(
            top_frame, text="Export .txt", command=self.on_export_txt
        )
        export_txt_btn.grid(row=0, column=4, sticky="e", padx=(12, 4))

        export_tsv_btn = ttk.Button(
            top_frame, text="Export .tsv", command=self.on_export_tsv
        )
        export_tsv_btn.grid(row=0, column=5, sticky="e")

        # Toggle full art
        self.show_art_check = ttk.Checkbutton(
            top_frame,
            text="Show full card art",
            variable=self.show_art_var,
            command=self.on_toggle_art,
        )
        self.show_art_check.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # Search / filter row
        ttk.Label(top_frame, text="Search:").grid(
            row=2, column=0, sticky="w", pady=(4, 0)
        )
        self.search_entry = ttk.Entry(
            top_frame, textvariable=self.search_var, width=30
        )
        self.search_entry.grid(row=2, column=1, columnspan=3, sticky="w", pady=(4, 0))
        self.search_entry.bind("<KeyRelease>", self.on_search_changed)

        # Owned filter
        ttk.Label(top_frame, text="Owned filter:").grid(
            row=2, column=4, sticky="e", padx=(8, 2), pady=(4, 0)
        )
        self.owned_filter_combo = ttk.Combobox(
            top_frame,
            textvariable=self.owned_filter_var,
            values=["All", "1", "2", "3+"],
            state="readonly",
            width=5,
        )
        self.owned_filter_combo.grid(row=2, column=5, sticky="w", pady=(4, 0))
        self.owned_filter_combo.bind("<<ComboboxSelected>>", self.on_filter_or_sort_changed)

        # Sort mode
        ttk.Label(top_frame, text="Sort by:").grid(
            row=2, column=6, sticky="e", padx=(8, 2), pady=(4, 0)
        )
        self.sort_combo = ttk.Combobox(
            top_frame,
            textvariable=self.sort_var,
            values=["Name", "Owned (desc)"],
            state="readonly",
            width=12,
        )
        self.sort_combo.grid(row=2, column=7, sticky="w", pady=(4, 0))
        self.sort_combo.bind("<<ComboboxSelected>>", self.on_filter_or_sort_changed)

        # ---- Row 1: table of owned cards (name + owned) ----
        table_frame = ttk.Frame(self)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            table_frame,
            columns=("owned",),
            show="tree headings",
            height=15,
        )
        self.tree.heading("#0", text="Card")
        self.tree.heading("owned", text="Owned")
        self.tree.column("#0", width=280, anchor="w")
        self.tree.column("owned", width=80, anchor="center")

        self.tree.grid(row=0, column=0, sticky="nsew")

        tree_scroll = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.tree.yview
        )
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)

        # ---- Row 2: card art gallery (scrollable) ----
        self.art_frame = ttk.LabelFrame(self, text="Card Art")
        self.art_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        self.art_frame.rowconfigure(0, weight=1)
        self.art_frame.columnconfigure(0, weight=1)

        self.art_canvas = tk.Canvas(self.art_frame, highlightthickness=0)
        self.art_canvas.grid(row=0, column=0, sticky="nsew")

        self.art_scrollbar = ttk.Scrollbar(
            self.art_frame, orient="vertical", command=self.art_canvas.yview
        )
        self.art_scrollbar.grid(row=0, column=1, sticky="ns")
        self.art_canvas.configure(yscrollcommand=self.art_scrollbar.set)

        self.art_inner = ttk.Frame(self.art_canvas)
        self.art_window = self.art_canvas.create_window(
            (0, 0), window=self.art_inner, anchor="nw"
        )

        self.art_inner.bind("<Configure>", self._on_art_inner_configure)
        self.art_canvas.bind("<Configure>", self._on_art_canvas_configure)

        # Initially, hide the art frame
        self.art_frame.grid_remove()

        # Participant change
        self.participant_combo.bind("<<ComboboxSelected>>", self.on_participant_changed)

        self.refresh_view()

    # ---- Utility: retrieve participant ----

    def get_current_participant(self) -> dict:
        name = self.participant_var.get()
        if not name:
            raise RuntimeError("No participant selected.")
        p = self.game_state.get_participant(name)
        self.game_state._ensure_participant_struct(p)
        return p

    # ---- Layout helpers for art gallery ----

    def _on_art_inner_configure(self, event):
        self.art_canvas.configure(scrollregion=self.art_canvas.bbox("all"))

    def _on_art_canvas_configure(self, event):
        canvas_width = event.width
        self.art_canvas.itemconfig(self.art_window, width=canvas_width)
        # Rebuild gallery with updated column count when canvas is resized
        if self.show_art_var.get() and self.art_inner.winfo_children():
            try:
                participant = self.get_current_participant()
                self._build_art_gallery(self._get_filtered_collection(participant))
            except Exception:
                pass

    # ---- Filtering & sorting helpers ----

    def _get_filtered_collection(self, participant: dict) -> dict:
        """
        Return a {card_name: owned} dict filtered by search text and owned filter.
        """
        collection = participant.get("card_collection", {})
        query = self.search_var.get().strip().lower()

        if query:
            collection = {
                name: owned
                for name, owned in collection.items()
                if query in name.lower()
            }

        owned_filter = self.owned_filter_var.get()
        if owned_filter == "1":
            collection = {n: o for n, o in collection.items() if o == 1}
        elif owned_filter == "2":
            collection = {n: o for n, o in collection.items() if o == 2}
        elif owned_filter == "3+":
            collection = {n: o for n, o in collection.items() if o >= 3}

        return collection

    def _iter_sorted_collection(self, collection: dict) -> list[tuple[str, int]]:
        """
        Return list of (card_name, owned) sorted according to sort_var.
        If sorting by Owned, treat owned > 3 as 3 for ordering purposes.
        """
        items = list(collection.items())
        sort_mode = self.sort_var.get()
        if sort_mode == "Owned (desc)":
            items.sort(
                key=lambda kv: (-min(kv[1], 3), kv[0].lower())
            )
        else:
            items.sort(key=lambda kv: kv[0].lower())
        return items

    # ---- Image loading for gallery ----

    def _load_card_image_gallery(self, card_name: str) -> ImageTk.PhotoImage | None:
        path = _card_image_path(self.game_state, card_name)
        if path is None:
            return None
        try:
            img = Image.open(path)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    # ---- Main refresh ----

    def refresh_view(self):
        """
        Refresh DP, tier, text list, and art gallery (if visible),
        applying the current search + owned filter + sort.
        """
        try:
            participant = self.get_current_participant()
        except Exception:
            self.dp_label_var.set("DP: -")
            self.tier_label_var.set("Tier: -")
            for row in self.tree.get_children():
                self.tree.delete(row)
            self.card_images_gallery.clear()
            self._clear_art_gallery()
            return

        self.dp_label_var.set(f"DP: {participant.get('dp', 0)}")
        self.tier_label_var.set(f"Tier: {participant.get('tier', 1)}")

        filtered_collection = self._get_filtered_collection(participant)

        # --- Refresh list (Treeview) ---
        for row in self.tree.get_children():
            self.tree.delete(row)

        for card_name, owned in self._iter_sorted_collection(filtered_collection):
            self.tree.insert(
                "",
                tk.END,
                text=card_name,
                values=(owned,),
            )

        # --- Refresh art gallery if visible ---
        if self.show_art_var.get():
            self._build_art_gallery(filtered_collection)
        else:
            self._clear_art_gallery()

    def _clear_art_gallery(self):
        for child in self.art_inner.winfo_children():
            child.destroy()
        self.card_images_gallery.clear()

    def _build_art_gallery(self, collection: dict):
        """
        Build a grid of 100x100 card art images with names and owned counts,
        using current sorting. Column count is computed from the canvas width.
        """
        self._clear_art_gallery()

        if not collection:
            return

        cell_w = 116  # 100px image + 8px padding each side
        canvas_width = self.art_canvas.winfo_width()
        columns = max(1, canvas_width // cell_w - 1)
        row = 0
        col = 0

        for card_name, owned in self._iter_sorted_collection(collection):
            img = self._load_card_image_gallery(card_name)

            card_frame = ttk.Frame(self.art_inner, padding=4)
            card_frame.grid(row=row, column=col, sticky="n")

            if img:
                lbl_img = ttk.Label(card_frame, image=img)
                lbl_img.pack()
                self.card_images_gallery[card_name] = img
            else:
                lbl_img = ttk.Label(
                    card_frame,
                    text="[No image]",
                    width=16,
                    anchor="center",
                )
                lbl_img.pack()

            lbl_text = ttk.Label(
                card_frame,
                text=f"{card_name}\n(Owned: {owned})",
                anchor="center",
                justify="center",
            )
            lbl_text.pack(pady=(2, 0))

            col += 1
            if col >= columns:
                col = 0
                row += 1

    # ---- Export handlers ----

    def on_export_txt(self):
        try:
            participant = self.get_current_participant()
        except Exception:
            messagebox.showwarning("Export .txt", "No participant selected.")
            return

        collection = participant.get("card_collection", {})
        if not collection:
            messagebox.showinfo("Export .txt", "No cards in collection to export.")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Export collection to .txt",
        )
        if not filename:
            return

        lines = []
        for card_name in sorted(collection.keys()):
            owned = collection[card_name]
            lines.append(f"{card_name} ({owned})")

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception as e:
            messagebox.showerror("Export .txt", f"Error exporting: {e}")
            return

        messagebox.showinfo("Export .txt", f"Collection exported to:\n{filename}")

    def on_export_tsv(self):
        try:
            participant = self.get_current_participant()
        except Exception:
            messagebox.showwarning("Export .tsv", "No participant selected.")
            return

        collection = participant.get("card_collection", {})
        if not collection:
            messagebox.showinfo("Export .tsv", "No cards in collection to export.")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".tsv",
            filetypes=[("TSV files", "*.tsv"), ("All files", "*.*")],
            title="Export collection to .tsv",
        )
        if not filename:
            return

        lines = ["Card\tOwned"]
        for card_name in sorted(collection.keys()):
            owned = collection[card_name]
            safe_name = card_name.replace("\t", " ")
            lines.append(f"{safe_name}\t{owned}")

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception as e:
            messagebox.showerror("Export .tsv", f"Error exporting: {e}")
            return

        messagebox.showinfo("Export .tsv", f"Collection exported to:\n{filename}")

    # ---- Event handlers ----

    def on_participant_changed(self, event=None):
        self.refresh_view()

    def on_toggle_art(self):
        """
        Show or hide the full card art gallery, using the filtered collection.
        """
        if self.show_art_var.get():
            self.art_frame.grid()
            try:
                participant = self.get_current_participant()
                filtered_collection = self._get_filtered_collection(participant)
            except Exception:
                filtered_collection = {}
            self._build_art_gallery(filtered_collection)
        else:
            self.art_frame.grid_remove()
            self._clear_art_gallery()

    def on_search_changed(self, event=None):
        self.refresh_view()

    def on_filter_or_sort_changed(self, event=None):
        self.refresh_view()


# =========================
# Main App
# =========================

class MainApp(tk.Tk):
    def __init__(self, base_path: Path):
        super().__init__()
        self.title("YGO EDOPro Minigame")

        # Load game state
        self.game_state = GameState(base_path)

        # Participant selection
        self.participant_var = tk.StringVar()
        participant_names = list(self.game_state.participants.keys())
        if participant_names:
            self.participant_var.set(participant_names[0])

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        # Shop tab
        self.shop_frame = ShopFrame(
            notebook,
            game_state=self.game_state,
            participant_var=self.participant_var,
            on_after_reset=self.on_after_reset,
            on_after_pack_open=self.on_after_pack_open,
        )
        notebook.add(self.shop_frame, text="Shop")

        # Duel Log tab
        self.duel_log_frame = DuelLogFrame(
            notebook,
            game_state=self.game_state,
            participant_var=self.participant_var,
            on_after_duel=self.on_after_duel,
        )
        notebook.add(self.duel_log_frame, text="Duels")

        # Collection tab
        self.collection_frame = CollectionFrame(
            notebook,
            game_state=self.game_state,
            participant_var=self.participant_var,
        )
        notebook.add(self.collection_frame, text="Collection")

    def on_after_duel(self):
        # After a duel, refresh everything that depends on DP/collection/tier
        self.shop_frame.refresh_view()
        self.collection_frame.refresh_view()
        self.duel_log_frame.refresh_view()

    def on_after_pack_open(self):
        self.collection_frame.refresh_view()

    def on_after_reset(self):
        # After reset, refresh everything
        self.shop_frame.refresh_view()
        self.collection_frame.refresh_view()
        self.duel_log_frame.refresh_view()


def main():
    base_path = Path("data")  # your JSON directory
    app = MainApp(base_path)
    app.mainloop()


if __name__ == "__main__":
    main()
