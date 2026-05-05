-- ============================================
-- NATGAME DATABASE SCHEMA
-- Discord Nation Simulation Game
-- Run this in Supabase SQL Editor
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. NATIONS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS nations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id BIGINT NOT NULL UNIQUE,  -- Discord user ID
    name TEXT NOT NULL,
    money INTEGER DEFAULT 1000,
    population INTEGER DEFAULT 100,
    army INTEGER DEFAULT 10,
    navy INTEGER DEFAULT 0,
    airforce INTEGER DEFAULT 0,
    last_recruit_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index cho owner_id lookups
CREATE INDEX idx_nations_owner ON nations(owner_id);

-- ============================================
-- 2. NATION LEVELS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS nation_levels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nation_id UUID NOT NULL REFERENCES nations(id) ON DELETE CASCADE,
    level INTEGER DEFAULT 1,
    exp INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(nation_id)
);

CREATE INDEX idx_nation_levels_nation ON nation_levels(nation_id);

-- ============================================
-- 3. MILITARY UNITS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS military_units (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nation_id UUID NOT NULL REFERENCES nations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    tier TEXT NOT NULL,  -- to, tieu_doi, trung_doi, dai_doi, tieu_doan, trung_doan, lu_doan, su_doan
    branch TEXT NOT NULL DEFAULT 'army',  -- army, navy, airforce
    size INTEGER NOT NULL,
    level INTEGER DEFAULT 1,
    exp INTEGER DEFAULT 0,
    status TEXT DEFAULT 'idle',  -- idle, war, defense
    war_army_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(nation_id, name)
);

CREATE INDEX idx_units_nation ON military_units(nation_id);
CREATE INDEX idx_units_status ON military_units(status);
CREATE INDEX idx_units_war_army ON military_units(war_army_id);

-- ============================================
-- 4. DEFENSE LINES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS defense_lines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nation_id UUID NOT NULL REFERENCES nations(id) ON DELETE CASCADE,
    slot INTEGER NOT NULL,
    unit_id UUID NOT NULL REFERENCES military_units(id) ON DELETE CASCADE,
    troops INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(nation_id, slot)
);

CREATE INDEX idx_defense_nation ON defense_lines(nation_id);
CREATE INDEX idx_defense_unit ON defense_lines(unit_id);

-- ============================================
-- 5. WAR ARMIES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS war_armies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nation_id UUID NOT NULL REFERENCES nations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'preparing',  -- preparing, deployed, returning
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_war_armies_nation ON war_armies(nation_id);

-- ============================================
-- 6. WAR ARMY UNITS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS war_army_units (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    war_army_id UUID NOT NULL REFERENCES war_armies(id) ON DELETE CASCADE,
    unit_id UUID REFERENCES military_units(id) ON DELETE SET NULL,
    troops INTEGER DEFAULT 0,  -- For loose troops
    loose_troops INTEGER DEFAULT 0,  -- Quân lẻ không thuộc unit
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_war_army_units_wa ON war_army_units(war_army_id);
CREATE INDEX idx_war_army_units_unit ON war_army_units(unit_id);

-- ============================================
-- 7. WARS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS wars (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    attacker_nation_id UUID NOT NULL REFERENCES nations(id) ON DELETE CASCADE,
    defender_nation_id UUID REFERENCES nations(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'active',  -- active, ongoing, finished
    winner_nation_id UUID REFERENCES nations(id) ON DELETE SET NULL,
    war_type TEXT DEFAULT 'pvp',  -- pvp, pve
    created_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ
);

CREATE INDEX idx_wars_attacker ON wars(attacker_nation_id);
CREATE INDEX idx_wars_defender ON wars(defender_nation_id);
CREATE INDEX idx_wars_status ON wars(status);

-- ============================================
-- 8. WAR ATTACK SNAPSHOT
-- ============================================
CREATE TABLE IF NOT EXISTS war_attack_snapshot (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    war_id UUID NOT NULL REFERENCES wars(id) ON DELETE CASCADE,
    unit_id UUID REFERENCES military_units(id) ON DELETE SET NULL,
    troops INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_attack_snapshot_war ON war_attack_snapshot(war_id);

-- ============================================
-- 9. WAR DEFENSE SNAPSHOT
-- ============================================
CREATE TABLE IF NOT EXISTS war_defense_snapshot (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    war_id UUID NOT NULL REFERENCES wars(id) ON DELETE CASCADE,
    slot INTEGER NOT NULL,
    unit_id UUID REFERENCES military_units(id) ON DELETE SET NULL,
    troops INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_defense_snapshot_war ON war_defense_snapshot(war_id);

-- ============================================
-- 10. WAR LOGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS war_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    war_id UUID NOT NULL REFERENCES wars(id) ON DELETE CASCADE,
    round INTEGER NOT NULL,
    phase TEXT NOT NULL,  -- defense, city
    attacker_loss INTEGER DEFAULT 0,
    defender_loss INTEGER DEFAULT 0,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_war_logs_war ON war_logs(war_id);

-- ============================================
-- RPC FUNCTIONS
-- ============================================

-- Function: nation_recruit
-- Tuyển quân từ dân số
CREATE OR REPLACE FUNCTION nation_recruit(p_user TEXT)
RETURNS TABLE(
    recruited INTEGER,
    money_spent INTEGER,
    army_after INTEGER,
    population_after INTEGER,
    money_after INTEGER
) AS $$
DECLARE
    v_nation RECORD;
    v_last_recruit TIMESTAMPTZ;
    v_cooldown_hours INTEGER := 1;
    v_recruit_cost INTEGER := 10;  -- Cost per soldier
    v_recruit_rate FLOAT := 0.1;  -- 10% of population
    v_max_recruit INTEGER;
    v_actual_recruit INTEGER;
    v_total_cost INTEGER;
BEGIN
    -- Get nation info
    SELECT id, army, population, money, last_recruit_at
    INTO v_nation
    FROM nations
    WHERE owner_id = p_user::BIGINT;

    IF v_nation IS NULL THEN
        RAISE EXCEPTION 'nation not found';
    END IF;

    -- Check cooldown
    IF v_nation.last_recruit_at IS NOT NULL THEN
        IF NOW() - v_nation.last_recruit_at < INTERVAL '1 hour' THEN
            RAISE EXCEPTION 'cooldown';
        END IF;
    END IF;

    -- Check population
    IF v_nation.population < 10 THEN
        RAISE EXCEPTION 'population too low';
    END IF;

    -- Calculate recruits
    v_max_recruit := FLOOR(v_nation.population * v_recruit_rate)::INTEGER;
    v_total_cost := v_max_recruit * v_recruit_cost;

    -- Check money
    IF v_nation.money < v_total_cost THEN
        -- Reduce recruits to match money
        v_max_recruit := FLOOR(v_nation.money / v_recruit_cost)::INTEGER;
        v_total_cost := v_max_recruit * v_recruit_cost;
    END IF;

    IF v_max_recruit <= 0 THEN
        RAISE EXCEPTION 'money not enough';
    END IF;

    v_actual_recruit := v_max_recruit;

    -- Update nation
    UPDATE nations
    SET army = army + v_actual_recruit,
        population = population - v_actual_recruit,
        money = money - v_total_cost,
        last_recruit_at = NOW(),
        updated_at = NOW()
    WHERE id = v_nation.id;

    RETURN QUERY
    SELECT 
        v_actual_recruit,
        v_total_cost,
        v_nation.army + v_actual_recruit,
        v_nation.population - v_actual_recruit,
        v_nation.money - v_total_cost;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Function: nation_convert
-- Chuyển quân Lục quân sang Navy/Airforce
CREATE OR REPLACE FUNCTION nation_convert(
    p_owner_id TEXT,
    p_amount INTEGER,
    p_branch TEXT
)
RETURNS TABLE(
    requested INTEGER,
    success INTEGER,
    failed INTEGER,
    final_army INTEGER,
    final_navy INTEGER,
    final_airforce INTEGER
) AS $$
DECLARE
    v_nation RECORD;
    v_success INTEGER;
    v_failed INTEGER;
    v_success_rate FLOAT := 0.7;  -- 70% success rate
BEGIN
    -- Get nation
    SELECT id, army, navy, airforce
    INTO v_nation
    FROM nations
    WHERE owner_id = p_owner_id::BIGINT;

    IF v_nation IS NULL THEN
        RAISE EXCEPTION 'nation not found';
    END IF;

    -- Check unlock requirements (level based)
    IF p_branch = 'navy' THEN
        -- Require level 3 for navy
        IF NOT EXISTS (SELECT 1 FROM nation_levels WHERE nation_id = v_nation.id AND level >= 3) THEN
            RAISE EXCEPTION 'Navy not unlocked';
        END IF;
    ELSIF p_branch = 'airforce' THEN
        -- Require level 5 for airforce
        IF NOT EXISTS (SELECT 1 FROM nation_levels WHERE nation_id = v_nation.id AND level >= 5) THEN
            RAISE EXCEPTION 'Airforce not unlocked';
        END IF;
    ELSE
        RAISE EXCEPTION 'Invalid branch';
    END IF;

    -- Check army availability
    IF v_nation.army < p_amount THEN
        RAISE EXCEPTION 'Not enough army';
    END IF;

    -- Calculate success/failure
    v_success := FLOOR(p_amount * v_success_rate)::INTEGER;
    v_failed := p_amount - v_success;

    -- Update nation
    IF p_branch = 'navy' THEN
        UPDATE nations
        SET army = army - p_amount + v_failed,
            navy = navy + v_success,
            updated_at = NOW()
        WHERE id = v_nation.id;
    ELSE
        UPDATE nations
        SET army = army - p_amount + v_failed,
            airforce = airforce + v_success,
            updated_at = NOW()
        WHERE id = v_nation.id;
    END IF;

    RETURN QUERY
    SELECT 
        p_amount,
        v_success,
        v_failed,
        v_nation.army - p_amount + v_failed,
        CASE WHEN p_branch = 'navy' THEN v_nation.navy + v_success ELSE v_nation.navy END,
        CASE WHEN p_branch = 'airforce' THEN v_nation.airforce + v_success ELSE v_nation.airforce END;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Function: nation_tick
-- Tick mỗi 10 phút - tăng dân số và tiền
CREATE OR REPLACE FUNCTION nation_tick()
RETURNS INTEGER AS $$
DECLARE
    v_updated INTEGER := 0;
BEGIN
    -- Tăng dân số (1% mỗi tick)
    UPDATE nations
    SET population = population + GREATEST(1, FLOOR(population * 0.01)::INTEGER),
        money = money + GREATEST(10, FLOOR(population * 0.1)::INTEGER),
        updated_at = NOW()
    WHERE id IS NOT NULL;  -- WHERE để tránh lỗi "UPDATE requires WHERE"

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RETURN v_updated;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Function: nation_maintenance_tick
-- Maintenance cost cho quân đội
CREATE OR REPLACE FUNCTION nation_maintenance_tick()
RETURNS VOID AS $$
DECLARE
    v_nation RECORD;
    v_maintenance INTEGER;
BEGIN
    FOR v_nation IN SELECT id, army, navy, airforce, money FROM nations
    LOOP
        -- 1 money per 10 troops
        v_maintenance := GREATEST(0, FLOOR((v_nation.army + v_nation.navy + v_nation.airforce) / 10)::INTEGER);
        
        IF v_nation.money >= v_maintenance THEN
            UPDATE nations
            SET money = money - v_maintenance,
                updated_at = NOW()
            WHERE id = v_nation.id;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Triggers
-- ============================================

-- Auto-create nation_level when nation created
CREATE OR REPLACE FUNCTION create_nation_level()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO nation_levels (nation_id, level, exp)
    VALUES (NEW.id, 1, 0);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_create_nation_level
    AFTER INSERT ON nations
    FOR EACH ROW
    EXECUTE FUNCTION create_nation_level();

-- ============================================
-- Sample Data (Optional - for testing)
-- ============================================

-- Uncomment để tạo test data
/*
INSERT INTO nations (owner_id, name, money, population, army)
VALUES 
    (123456789, 'Test Nation 1', 5000, 500, 50),
    (987654321, 'Test Nation 2', 3000, 300, 30);
*/

-- ============================================
-- END OF SCHEMA
-- ============================================
