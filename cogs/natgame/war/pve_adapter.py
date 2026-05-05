from .war_adapter import WarAdapter
from cogs.natgame.war.combat_engine import CombatEngine

class PVEAdapter(WarAdapter):
    """Adapter cho PVE combat - đánh với AI"""

    # Cấu hình độ khó PVE theo level
    PVE_DIFFICULTY = {
        "easy": {
            "defense_lines": [
                {"slot": 1, "unit_id": None, "troops": 50},
            ],
            "garrison": {"army": 30, "idle_units": []}
        },
        "medium": {
            "defense_lines": [
                {"slot": 1, "unit_id": None, "troops": 60},
                {"slot": 2, "unit_id": None, "troops": 90},
            ],
            "garrison": {"army": 120, "idle_units": []}
        },
        "hard": {
            "defense_lines": [
                {"slot": 1, "unit_id": None, "troops": 100},
                {"slot": 2, "unit_id": None, "troops": 150},
                {"slot": 3, "unit_id": None, "troops": 200},
            ],
            "garrison": {"army": 300, "idle_units": []}
        }
    }

    def get_pve_difficulty(self, attacker_army_size: int) -> str:
        """Chọn độ khó dựa trên quân số attacker"""
        if attacker_army_size < 100:
            return "easy"
        elif attacker_army_size < 500:
            return "medium"
        else:
            return "hard"

    def run_war(self, war_id: str, attacker_id: str = None, difficulty: str = None):
        """
        Chạy PVE combat
        
        Args:
            war_id: ID của war record
            attacker_id: nation_id của attacker (optional)
            difficulty: 'easy', 'medium', 'hard' (auto-detect nếu None)
        """
        # Load attacker snapshot từ war record
        attacker_army = self.load_attacker_snapshot(war_id)
        
        if not attacker_army:
            return {
                "result": "error",
                "message": "No attacker army found",
                "attacker_remaining": 0,
                "defender_remaining": 0,
                "logs": []
            }

        # Tính tổng quân attacker để chọn độ khó
        total_attackers = sum(a["troops"] for a in attacker_army)
        
        if difficulty is None:
            difficulty = self.get_pve_difficulty(total_attackers)
        
        # Load defense theo độ khó
        difficulty_config = self.PVE_DIFFICULTY.get(difficulty, self.PVE_DIFFICULTY["medium"])
        defense_lines = difficulty_config["defense_lines"]
        garrison = difficulty_config["garrison"]

        # Tạo combat engine với PVE setup
        engine = CombatEngine(
            attacker_army=attacker_army,
            defense_lines=defense_lines,
            garrison=garrison
        )

        # Chạy combat
        result = engine.run()

        # Thêm metadata
        result["war_id"] = war_id
        result["difficulty"] = difficulty
        result["attacker_id"] = attacker_id

        # NOTE: apply_result được gọi bởi WarService.resolve_war()
        # Không gọi lại ở đây để tránh duplicate logs
        return result
