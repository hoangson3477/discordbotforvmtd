# cogs/utils.py
import logging
import aiohttp

log = logging.getLogger('my_bot')

# --- CÁC HÀM TIỆN ÍCH DÙNG AIOHTTP ---

async def get_roblox_id_from_username(session: aiohttp.ClientSession, username: str):
    """Lấy Roblox ID từ username một cách bất đồng bộ."""
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {'usernames': [username], 'excludeBannedUsers': True}
    try:
        async with session.post(url, json=payload) as response:
            response.raise_for_status()
            data = await response.json()
            if data and data.get('data'):
                return data['data'][0]['id']
            return None
    except Exception as e:
        log.error(f"Lỗi aiohttp khi lấy Roblox ID từ username '{username}': {e}")
        return None

async def get_roblox_username_from_id(session: aiohttp.ClientSession, user_id: int):
    """Lấy Roblox username từ ID một cách bất đồng bộ."""
    url = f"https://users.roblox.com/v1/users/{user_id}"
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()
            if data and 'name' in data:
                return data['name']
            return None
    except Exception as e:
        log.error(f"Lỗi aiohttp khi lấy thông tin người dùng (ID: {user_id}): {e}")
        return None

async def get_roblox_user_rank_in_group(session: aiohttp.ClientSession, roblox_user_id: int, group_id: int):
    """Lấy rank (dạng số 0-255) của một người dùng trong một group cụ thể."""
    url = f"https://groups.roblox.com/v1/users/{roblox_user_id}/groups/roles"
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()
            data = data.get('data', [])
            
            for group_data in data:
                if str(group_data['group']['id']) == str(group_id):
                    return group_data['role']['rank']
            return 0
    except Exception as e:
        log.error(f"Lỗi aiohttp khi gọi Roblox Group API cho user {roblox_user_id}, group {group_id}: {e}")
        return None

# Thêm hàm này vào cuối file cogs/utils.py
async def get_roblox_user_description(session: aiohttp.ClientSession, user_id: int):
    """Lấy mô tả (description/about) của user Roblox từ ID."""
    url = f"https://users.roblox.com/v1/users/{user_id}"
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get('description', '')
    except Exception as e:
        log.error(f"Lỗi aiohttp khi lấy description cho user (ID: {user_id}): {e}")
        return None
    
async def get_roblox_user_groups(session: aiohttp.ClientSession, roblox_user_id: int):
    """Lấy danh sách các nhóm mà một người dùng Roblox đang tham gia."""
    url = f"https://groups.roblox.com/v1/users/{roblox_user_id}/groups/roles"
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()
            return data.get('data', [])
    except Exception as e:
        log.error(f"Lỗi aiohttp khi gọi Roblox Group API cho user {roblox_user_id}: {e}")
        return []