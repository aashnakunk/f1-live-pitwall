import fastf1

# enable cache (important)
fastf1.Cache.enable_cache('cache')

# Load session
session = fastf1.get_session(2026, 'Australia', 'Q')
session.load()

# Show fastest lap
lap = session.laps.pick_fastest()
print("Fastest Lap Driver:", lap['Driver'])
print("Lap Time:", lap['LapTime'])