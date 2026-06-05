import re

with open('webapp/app/crawler_runner.py', 'r') as f:
    content = f.read()

# Update _script_command_for_osm to handle anchor and radius from config
# The current implementation might already handle it if they are in config.
# Let's check the function definition.
