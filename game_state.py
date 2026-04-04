from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

PACK_OPEN_SOUND_RELATIVE = "sounds/pack_open.wav"

# Canonical rarity names and their pull weights.
RARITY_WEIGHTS: Dict[str, float] = {
    "Common": 0.75,
    "Rare": 0.18,
    "Super Rare": 0.06,
    "Ultra Rare": 0.0067,
    "Secret Rare": 0.0033,
}

# Aliases that map short forms to the canonical names above.
_RARITY_ALIASES: Dict[str, str] = {
    "C": "Common",
    "R": "Rare",
    "SR": "Super Rare",
    "UR": "Ultra Rare",
    "ScR": "Secret Rare",
}


class GameState:
    """
    Core game state: cards, packs, duelists, participants.
    Handles pack opening and card buying logic (no UI).
    """

    def __init__(self, base_path: Path | str, default_cards_per_pack: int = 5) -> None:
        self.base_path = Path(base_path)
        self.default_cards_per_pack = default_cards_per_pack

        self.cards: Dict[str, Dict[str, Any]] = self._load_json("cards.json")
        self.duelists: Dict[str, Dict[str, Any]] = self._load_json("duelists.json")
        self.participants: Dict[str, Dict[str, Any]] = self._load_json("participants.json")

        # packs.json provides optional metadata overrides; card_lists drive the actual packs.
        _packs_meta: Dict[str, Dict[str, Any]] = self._load_json("packs.json")
        self.packs: Dict[str, Dict[str, Any]] = self._load_card_lists_as_packs(_packs_meta)

        # name -> id lookup built from output/cardinfo.json
        self.cardinfo_name_to_id: Dict[str, int] = self._load_cardinfo_name_to_id()

    # ---------- JSON IO ----------

    def _load_cardinfo_name_to_id(self) -> Dict[str, int]:
        """Load output/cardinfo.json and return a name -> id mapping."""
        path = self.base_path.parent / "output" / "cardinfo.json"
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return {card["name"]: card["id"] for card in data.get("data", [])}

    def _load_card_lists_as_packs(
        self, packs_meta: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build the pack catalog from output/card_lists/*.json.
        Each JSON file becomes one pack keyed by its stem name.
        packs_meta (from packs.json) may override display_name, unlock_cost,
        pack_cost, cards_per_pack, and unlock_requirements for any pack.
        Packs with no cards of a supported rarity are skipped.
        """
        card_lists_dir = self.base_path.parent / "output" / "card_lists"
        if not card_lists_dir.exists():
            return {}

        packs: Dict[str, Dict[str, Any]] = {}

        for json_path in sorted(card_lists_dir.glob("*.json")):
            pack_key = json_path.stem
            with json_path.open("r", encoding="utf-8") as f:
                card_data: Dict[str, List[str]] = json.load(f)

            # Build cards_by_rarity using canonical rarity names.
            cards_by_rarity: Dict[str, List[str]] = {r: [] for r in RARITY_WEIGHTS}
            for card_name, rarities in card_data.items():
                for rarity in rarities:
                    canonical = _RARITY_ALIASES.get(rarity, rarity)
                    if canonical in RARITY_WEIGHTS:
                        cards_by_rarity[canonical].append(card_name)

            # Skip packs that have no pullable cards at all.
            if not any(cards_by_rarity.values()):
                continue

            meta = packs_meta.get(pack_key, {})
            packs[pack_key] = {
                "display_name": meta.get("display_name", pack_key),
                "unlock_cost": meta.get("unlock_cost", 0),
                "pack_cost": meta.get("pack_cost", 0),
                "cards_per_pack": meta.get("cards_per_pack", self.default_cards_per_pack),
                "unlock_requirements": meta.get("unlock_requirements", {"tier_min": 1}),
                "_cards_by_rarity": cards_by_rarity,
            }

        return packs

    def _load_json(self, filename: str) -> Dict[str, Any]:
        path = self.base_path / filename
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save_json(self, filename: str, data: Dict[str, Any]) -> None:
        path = self.base_path / filename
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save_participants(self) -> None:
        self._save_json("participants.json", self.participants)

    # ---------- Helpers ----------

    def get_participant(self, name: str) -> Dict[str, Any]:
        if name not in self.participants:
            raise KeyError(f"Unknown participant: {name}")
        return self.participants[name]

    def _ensure_participant_struct(self, participant: Dict[str, Any]) -> None:
        """
        Ensure optional fields exist so the rest of the code can assume them.
        Useful if you hand-edit JSON and forget some keys.
        """
        participant.setdefault("dp", 0)
        participant.setdefault("tier", 1)
        participant.setdefault("unlocked_packs", [])
        participant.setdefault("unlocked_cards", [])
        participant.setdefault("card_collection", {})
        participant.setdefault("beat_counts", {})     # duelist_name -> wins
        participant.setdefault("duel_history", [])

    # ---------- Pack / card helpers ----------

    def _open_pack_raw(self, pack_def: Dict[str, Any]) -> List[str]:
        """
        Open a pack definition and return a list of card names (no side effects).
        Rarity is chosen by RARITY_WEIGHTS; only rarities with at least one card
        in this pack are eligible.
        """
        cards_per_pack = pack_def.get("cards_per_pack", self.default_cards_per_pack)
        cards_by_rarity: Dict[str, List[str]] = pack_def["_cards_by_rarity"]

        available = [(r, RARITY_WEIGHTS[r]) for r in RARITY_WEIGHTS if cards_by_rarity.get(r)]
        if not available:
            return []

        rarities, weights = zip(*available)

        opened: List[str] = []
        for _ in range(cards_per_pack):
            rarity = random.choices(rarities, weights=weights, k=1)[0]
            opened.append(random.choice(cards_by_rarity[rarity]))

        return opened

    def _add_card_to_collection(self, participant: Dict[str, Any], card_name: str) -> bool:
        """
        Add one copy of card_name to the participant's collection if they don't already
        have max copies. Returns True if added, False otherwise.

        Cards do not need to be defined in cards.json — any card that exists in
        cardinfo.json (by name) is valid. cards.json only provides overrides for
        max_copies, price, and unlock requirements.
        """
        self._ensure_participant_struct(participant)

        # Card must exist in cardinfo (or have an explicit entry in cards.json)
        if card_name not in self.cards and card_name not in self.cardinfo_name_to_id:
            return False

        card_def = self.cards.get(card_name, {})
        max_copies: int = card_def.get("max_copies", 3)

        collection = participant["card_collection"]
        current = collection.get(card_name, 0)

        if current >= max_copies:
            return False

        collection[card_name] = current + 1
        return True

    # ---------- Unlock requirement checking ----------

    @staticmethod
    def _meets_unlock_requirements(
        requirements: Optional[Dict[str, Any]],
        participant: Dict[str, Any],
    ) -> bool:
        """
        Check generic unlock requirements of the form:
        {
            "tier_min": 2,
            "beat_duelist_counts": {
                "Yugi Muto": 3,
                "Joey Wheeler": 1
            }
        }
        """
        if not requirements:
            return True

        tier_min = requirements.get("tier_min")
        if tier_min is not None:
            if participant.get("tier", 1) < tier_min:
                return False

        beat_req = requirements.get("beat_duelist_counts", {})
        beat_counts = participant.get("beat_counts", {})

        for duelist_name, needed in beat_req.items():
            if beat_counts.get(duelist_name, 0) < needed:
                return False

        return True

    # ---------- Public API: packs ----------

    def can_unlock_pack(self, participant_name: str, pack_name: str) -> tuple[bool, str]:
        participant = self.get_participant(participant_name)
        self._ensure_participant_struct(participant)

        if pack_name not in self.packs:
            return False, f"Unknown pack: {pack_name}"

        if pack_name in participant["unlocked_packs"]:
            return False, f"Pack '{pack_name}' is already unlocked."

        pack_def = self.packs[pack_name]
        unlock_cost = pack_def.get("unlock_cost", 0)
        requirements = pack_def.get("unlock_requirements")

        if not self._meets_unlock_requirements(requirements, participant):
            return False, "Unlock requirements are not met."

        if participant["dp"] < unlock_cost:
            return False, f"Not enough DP (need {unlock_cost}, have {participant['dp']})."

        return True, "OK"

    def unlock_pack(self, participant_name: str, pack_name: str) -> bool:
        ok, reason = self.can_unlock_pack(participant_name, pack_name)
        if not ok:
            print(f"Cannot unlock pack: {reason}")
            return False

        participant = self.get_participant(participant_name)
        pack_def = self.packs[pack_name]
        unlock_cost = pack_def.get("unlock_cost", 0)

        participant["dp"] -= unlock_cost
        participant["unlocked_packs"].append(pack_name)
        self.save_participants()
        return True

    def can_buy_pack(self, participant_name: str, pack_name: str) -> tuple[bool, str]:
        participant = self.get_participant(participant_name)
        self._ensure_participant_struct(participant)

        if pack_name not in self.packs:
            return False, f"Unknown pack: {pack_name}"

        if pack_name not in participant["unlocked_packs"]:
            return False, f"Pack '{pack_name}' is not unlocked yet."

        pack_def = self.packs[pack_name]
        pack_cost = pack_def.get("pack_cost", 0)

        if participant["dp"] < pack_cost:
            return False, f"Not enough DP (need {pack_cost}, have {participant['dp']})."

        return True, "OK"

    def open_pack_for_participant(
        self,
        participant_name: str,
        pack_name: str,
        *,
        pay_with_dp: bool = True,
        require_unlocked: bool = True,
    ) -> List[str]:
        """
        Open a pack for a participant.
        - If pay_with_dp is True, subtract pack_cost DP.
        - If require_unlocked is True, participant must have previously unlocked the pack.
        Returns the list of card names pulled.
        """
        participant = self.get_participant(participant_name)
        self._ensure_participant_struct(participant)

        if pack_name not in self.packs:
            raise KeyError(f"Unknown pack: {pack_name}")

        pack_def = self.packs[pack_name]

        if require_unlocked and pack_name not in participant["unlocked_packs"]:
            raise ValueError(f"Pack '{pack_name}' is not unlocked for participant '{participant_name}'.")

        pack_cost = pack_def.get("pack_cost", 0)
        if pay_with_dp:
            if participant["dp"] < pack_cost:
                raise ValueError(
                    f"Not enough DP to buy pack '{pack_name}' "
                    f"(need {pack_cost}, have {participant['dp']})."
                )
            participant["dp"] -= pack_cost

        opened_cards = self._open_pack_raw(pack_def)

        # Add cards to collection, respecting max copies.
        for card_name in opened_cards:
            self._add_card_to_collection(participant, card_name)

        self.save_participants()
        return opened_cards

    # ---------- Public API: cards ----------

    def can_unlock_card(self, participant_name: str, card_name: str) -> tuple[bool, str]:
        participant = self.get_participant(participant_name)
        self._ensure_participant_struct(participant)

        if card_name not in self.cards:
            return False, f"Unknown card: {card_name}"

        if card_name in participant["unlocked_cards"]:
            return False, f"Card '{card_name}' is already unlocked."

        card_def = self.cards[card_name]
        requirements = card_def.get("unlock_requirements")

        if not self._meets_unlock_requirements(requirements, participant):
            return False, "Unlock requirements are not met."

        unlock_cost = card_def.get("unlock_cost")
        if unlock_cost is None:
            # Card does not require unlock (only per-copy purchases)
            return False, f"Card '{card_name}' does not have an unlock_cost; no unlock needed."

        if participant["dp"] < unlock_cost:
            return False, f"Not enough DP (need {unlock_cost}, have {participant['dp']})."

        return True, "OK"

    def unlock_card(self, participant_name: str, card_name: str) -> bool:
        ok, reason = self.can_unlock_card(participant_name, card_name)
        if not ok:
            print(f"Cannot unlock card: {reason}")
            return False

        participant = self.get_participant(participant_name)
        card_def = self.cards[card_name]
        unlock_cost = card_def.get("unlock_cost", 0)

        participant["dp"] -= unlock_cost
        participant["unlocked_cards"].append(card_name)
        self.save_participants()
        return True

    def can_buy_card_copy(self, participant_name: str, card_name: str) -> tuple[bool, str]:
        participant = self.get_participant(participant_name)
        self._ensure_participant_struct(participant)

        if card_name not in self.cards:
            return False, f"Unknown card: {card_name}"

        card_def = self.cards[card_name]

        # If card requires unlock first, enforce that.
        if card_def.get("unlock_cost") is not None and card_name not in participant["unlocked_cards"]:
            return False, f"Card '{card_name}' is not unlocked yet."

        price = card_def.get("price")
        if price is None:
            return False, f"Card '{card_name}' is not purchasable."

        if participant["dp"] < price:
            return False, f"Not enough DP (need {price}, have {participant['dp']})."

        max_copies: int = card_def.get("max_copies", 3)
        collection = participant["card_collection"]
        current = collection.get(card_name, 0)

        if current >= max_copies:
            return False, f"Already have max copies ({max_copies}) of '{card_name}'."

        return True, "OK"

    def buy_card_copy(self, participant_name: str, card_name: str) -> bool:
        ok, reason = self.can_buy_card_copy(participant_name, card_name)
        if not ok:
            print(f"Cannot buy card: {reason}")
            return False

        participant = self.get_participant(participant_name)
        card_def = self.cards[card_name]
        price = card_def.get("price", 0)

        participant["dp"] -= price
        self._add_card_to_collection(participant, card_name)
        self.save_participants()
        return True
    
    # ---------- Public API: duels ----------

    # ---------- Public API: duels ----------

    def record_duel(
        self,
        participant_name: str,
        opponent_name: str,
        result: str,
        role: str = "participant",
    ) -> dict:
        """
        Record a duel for a participant.

        - participant_name: which profile this log belongs to
        - opponent_name: string label (e.g., "Yugi Muto", "Joey Wheeler", "Mergo", or any custom name)
        - result: "win", "loss", or "draw"
        - role: "participant" if this profile was the human player,
                "npc" if this profile was acting as an NPC.

        Rewards (DP + free pack) are only given when:
        - role == "participant"
        - result == "win"
        - opponent_name is a known duelist in duelists.json

        Free pack is chosen as:
        - if duelist has "free_pack_rewards": weighted random choice among them
        - elif duelist has "free_pack_reward": that single pack
        - else: no free pack
        """
        participant = self.get_participant(participant_name)
        self._ensure_participant_struct(participant)

        result = result.lower()
        if result not in ("win", "loss", "draw"):
            raise ValueError(f"Invalid result: {result!r}")

        role = role.lower()
        if role not in ("participant", "npc"):
            raise ValueError(f"Invalid role: {role!r}")

        duelist_def = self.duelists.get(opponent_name)
        dp_change = 0
        free_pack: Optional[str] = None

        # Only give rewards if this profile was the human player and they won
        if role == "participant" and result == "win" and duelist_def is not None:
            dp_reward = duelist_def.get("dp_reward", 0)
            participant["dp"] += dp_reward
            dp_change = dp_reward

            # Increment beat count for unlock tracking
            beat_counts = participant.setdefault("beat_counts", {})
            beat_counts[opponent_name] = beat_counts.get(opponent_name, 0) + 1

            # Update tier based on beat_counts
            self._update_tier_from_beats(participant)

            # Weighted free pack selection
            free_packs = duelist_def.get("free_pack_rewards")
            if isinstance(free_packs, list) and free_packs:
                packs = []
                weights = []
                for item in free_packs:
                    pack_name = item.get("pack")
                    weight = float(item.get("weight", 1.0))
                    if pack_name is None:
                        continue
                    packs.append(pack_name)
                    weights.append(weight)
                if packs:
                    free_pack = random.choices(packs, weights=weights, k=1)[0]
            else:
                # Fallback to simple single pack
                free_pack = duelist_def.get("free_pack_reward")

        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "opponent": opponent_name,
            "result": result,
            "role": role,
            "dp_change": dp_change,
        }
        if free_pack is not None:
            entry["free_pack"] = free_pack

        participant["duel_history"].append(entry)
        self.save_participants()

        return {
            "dp_change": dp_change,
            "free_pack": free_pack,
        }

    # ---------- Tier progression ----------

    def _update_tier_from_beats(self, participant: dict) -> None:
        """
        Auto-update participant['tier'] based on beat_counts and duelist tiers.
        Rule:
          For each duelist tier T, if participant has beaten *all* duelists of tier T
          at least once, participant tier becomes at least T+1.
        """
        beat_counts = participant.get("beat_counts", {})
        current_tier = participant.get("tier", 1)

        # Group duelists by tier
        duelists_by_tier: dict[int, list[str]] = {}
        for name, d in self.duelists.items():
            t = d.get("tier")
            if isinstance(t, int):
                duelists_by_tier.setdefault(t, []).append(name)

        # Check tiers in ascending order
        new_tier = current_tier
        for t, names in duelists_by_tier.items():
            if not names:
                continue
            # Have we beaten *all* duelists of this tier at least once?
            if all(beat_counts.get(n, 0) >= 1 for n in names):
                # Tier becomes at least T+1
                new_tier = max(new_tier, t + 1)

        participant["tier"] = new_tier

    # ---------- Participant management ----------

    def reset_participant(self, participant_name: str) -> None:
        """
        Reset a participant's progress:
        - DP -> 0
        - tier -> 1
        - unlocked packs/cards cleared
        - card collection cleared
        - beat counts + duel history cleared
        """
        participant = self.get_participant(participant_name)

        participant["dp"] = 0
        participant["tier"] = 1
        participant["unlocked_packs"] = []
        participant["unlocked_cards"] = []
        participant["card_collection"] = {}
        participant["beat_counts"] = {}
        participant["duel_history"] = []

        self.save_participants()
