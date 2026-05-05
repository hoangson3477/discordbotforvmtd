from .combat_engine import CombatEngine
from cogs.natgame.__db import supabase
import datetime

class WarAdapter:
    def __init__(self, supabase):
        self.db = supabase

    def load_attacker_snapshot(self, war_id):
        rows = self.db.table("war_attack_snapshot") \
            .select("unit_id, troops") \
            .eq("war_id", war_id) \
            .execute().data

        return [{"id": r["unit_id"], "troops": r["troops"]} for r in rows]

    def load_defense_snapshot(self, war_id):
        rows = self.db.table("war_defense_snapshot") \
            .select("slot, unit_id, troops") \
            .eq("war_id", war_id) \
            .order("slot") \
            .execute().data

        return [
            {"slot": r["slot"], "unit_id": r["unit_id"], "troops": r["troops"]}
            for r in rows
        ]

    def run_war(self, war_id):
        attacker_army = self.load_attacker_snapshot(war_id)
        defense_lines = self.load_defense_snapshot(war_id)

        engine = CombatEngine(
            attacker_army=attacker_army,
            defense_lines=defense_lines,
            garrison={"army": 0, "idle_units": []}
        )

        return engine.run()

    def apply_result(self, war_id, result):
        # 1. Log combat
        for log in result["logs"]:
            self.db.table("war_logs").insert({
                "war_id": war_id,
                "round": log["round"],
                "phase": log["phase"],
                "attacker_loss": log["attacker_loss"],
                "defender_loss": log["defender_loss"],
                "description": log["description"]
            }).execute()

        war = self.db.table("wars") \
            .select("attacker_nation_id, defender_nation_id") \
            .eq("id", war_id) \
            .single().execute().data

        winner = (
            war["attacker_nation_id"]
            if result["result"] == "attacker_win"
            else war["defender_nation_id"]
        )

        self.db.table("wars").update({
            "status": "finished",
            "winner_nation_id": winner
        }).eq("id", war_id).execute()

        # 2. Apply casualties cho attacker
        self._apply_attacker_casualties(war_id, war["attacker_nation_id"], result)

        # 3. Apply casualties cho defender (nếu có - PvP)
        if war.get("defender_nation_id"):
            self._apply_defender_casualties(war_id, war["defender_nation_id"], result)

    def _apply_attacker_casualties(self, war_id, nation_id, result):
        """Trừ quân attacker theo kết quả combat"""
        # Tính tổng thiệt hại attacker
        total_attacker_loss = sum(log["attacker_loss"] for log in result["logs"])

        if total_attacker_loss <= 0:
            return

        # Lấy war army units
        war_units = self.db.table("war_attack_snapshot") \
            .select("unit_id, troops") \
            .eq("war_id", war_id) \
            .execute().data

        remaining_loss = total_attacker_loss

        for unit in war_units:
            if remaining_loss <= 0:
                break

            unit_id = unit.get("unit_id")
            original_troops = unit["troops"]

            if unit_id:
                # Unit thực - cập nhật military_units
                loss_for_this_unit = min(remaining_loss, original_troops)
                new_size = original_troops - loss_for_this_unit

                if new_size <= 0:
                    # Unit bị tiêu diệt hoàn toàn - xóa khỏi DB (auto-disband)
                    self.db.table("military_units").delete().eq("id", unit_id).execute()
                    # Log đã auto-disband
                    self.db.table("event_logs").insert({
                        "nation_id": nation_id,
                        "event_type": "unit_disbanded",
                        "event_data": {"reason": "destroyed_in_combat", "unit_id": unit_id}
                    }).execute()
                else:
                    # Unit còn sống - update size
                    self.db.table("military_units").update({
                        "size": new_size
                    }).eq("id", unit_id).execute()

                remaining_loss -= loss_for_this_unit
            else:
                # Loose troops - trừ từ nations.army
                loss_for_loose = min(remaining_loss, original_troops)

                nation = self.db.table("nations").select("army").eq("id", nation_id).single().execute().data
                if nation:
                    new_army = max(0, nation["army"] - loss_for_loose)
                    self.db.table("nations").update({"army": new_army}).eq("id", nation_id).execute()

                remaining_loss -= loss_for_loose

    def _apply_defender_casualties(self, war_id, nation_id, result):
        """Trừ quân defender theo kết quả combat"""
        total_defender_loss = sum(log["defender_loss"] for log in result["logs"])

        if total_defender_loss <= 0:
            return

        # Lấy defense snapshot
        defense_units = self.db.table("war_defense_snapshot") \
            .select("unit_id, troops") \
            .eq("war_id", war_id) \
            .execute().data

        remaining_loss = total_defender_loss

        for unit in defense_units:
            if remaining_loss <= 0:
                break

            unit_id = unit.get("unit_id")
            original_troops = unit["troops"]

            if unit_id:
                # Unit trong defense line
                loss_for_unit = min(remaining_loss, original_troops)
                new_size = original_troops - loss_for_unit

                if new_size <= 0:
                    # Unit bị phá hủy hoàn toàn - auto-disband
                    self.db.table("defense_lines").delete().eq("unit_id", unit_id).execute()
                    self.db.table("military_units").delete().eq("id", unit_id).execute()
                    # Log
                    self.db.table("event_logs").insert({
                        "nation_id": nation_id,
                        "event_type": "defense_unit_destroyed",
                        "event_data": {"unit_id": unit_id, "reason": "defense_destroyed"}
                    }).execute()
                else:
                    # Unit còn sống - update size, trả về idle
                    self.db.table("military_units").update({
                        "size": new_size,
                        "status": "idle",
                        "defense_line_slot": None
                    }).eq("id", unit_id).execute()
                    # Xóa khỏi defense line (unit đã rút về)
                    self.db.table("defense_lines").delete().eq("unit_id", unit_id).execute()

                remaining_loss -= loss_for_unit
            else:
                # Garrison troops - trừ từ nations.army
                loss_for_garrison = min(remaining_loss, original_troops)

                nation = self.db.table("nations").select("army").eq("id", nation_id).single().execute().data
                if nation:
                    new_army = max(0, nation["army"] - loss_for_garrison)
                    self.db.table("nations").update({"army": new_army}).eq("id", nation_id).execute()

                remaining_loss -= loss_for_garrison
