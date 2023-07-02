import discord
from discord import app_commands
from discord.ext import commands, tasks
import re

import os
from dotenv import load_dotenv

import asyncio

import requests
from datetime import date
from datetime import datetime, timedelta, timezone, time

load_dotenv()

REQUEST_URL = 'https://sc2arcade.com/api/lobbies/history?regionId=1&mapId=320612&includeMatchResult=true&limit=20'

TOKEN = os.getenv("DISCORD_TOKEN")

description = '''Island Defense Bot'''

intents = discord.Intents.default()
intents.message_content = True
GLOBAL_GUILDS = {}
MESSAGE_MAPPING = {} # mapping of lobby bot message id to island defense bot message

ALARM_TIME = time(hour=0, tzinfo=timezone.utc)

bot = commands.Bot(command_prefix='/', description=description, intents=intents)

@commands.guild_only()
@bot.hybrid_command(name="armor", description='Calculate the damage reduction', with_app_command=True)
async def armor(ctx: commands.Context, armor: int):
    try:
        i = int(armor)
    except ValueError:
        await ctx.send('You can only type a number')
        return
    v = (i*.06)/(1+0.06*i)
    await ctx.send('Damage reduction for armour %d percentage %.2f' % (i, v))
    
@commands.guild_only()
@bot.command()
@commands.is_owner()
async def sync(ctx, all=False):
    print('syncing commands')
    if not all:
        bot.tree.copy_global_to(guild=ctx.guild)
        await bot.tree.sync(guild=ctx.guild)
    else:
        for guild_id in GLOBAL_GUILDS:
            guild = GLOBAL_GUILDS[guild_id]
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
        await bot.tree.sync()
    
async def create_roles_for_guild(guild):
    private_house_role = discord.utils.get(guild.roles, name=f'lobby_broadcast_status_channel')
    if private_house_role is None:
        private_house_role = await guild.create_role(name=f'lobby_broadcast_status_channel')

async def setup_guild(guild):
    await create_default_channels_for_guild(guild)
    #await create_roles_for_guild(guild) # create roles for guild 
    
async def create_default_channels_for_guild(guild):
    channel = discord.utils.find(lambda c: c.name.startswith('Games This Week'), guild.channels)
    if channel is None:
        perms = discord.PermissionOverwrite(**{'speak': False, 'view_channel': True, 'connect': False})
        bot_owner = discord.PermissionOverwrite(**{'speak': False, 'view_channel': True, 'connect': True})
        channel = await guild.create_voice_channel('Games This Week 0', position=0, overwrites={guild.default_role: perms, guild.me: bot_owner})

@bot.event
async def on_guild_join(guild):
    GLOBAL_GUILDS[guild.id] = guild
    await setup_guild(guild)
        
@bot.event
async def on_guild_join(guild):
    GLOBAL_GUILDS[guild.id] = guild
    
@bot.event
async def on_message_edit(before, after):
    if after is not None:
        channel = after.channel
        author = after.author
        guild_id = after.guild.id
        message_id = after.id
    if not author.bot or author.name != 'Arcade Watcher' or after is None:
        return
    if message_id not in MESSAGE_MAPPING:
        print('not tracking')
        # we aren't tracking ignore
        return
    # let's check if we can parse how many players
    if after is not None and len(after.embeds[0].fields) > 1:
        name = after.embeds[0].fields[1].name
        status = after.embeds[0].fields[0].value.strip()
        actual_status = re.sub('[^A-Z]', '', status)
        print(actual_status)
        if name.startswith('Players'):
            array = name.split(' ')
            lobby_tuple = MESSAGE_MAPPING[message_id]
            lobby_message_id = lobby_tuple[0]
            if lobby_message_id is None: # we have not create a message yet lets check if we can
                split_array = array[1].split('/')
                if len(split_array) > 1:
                    num = int(split_array[0][1:])
                else:
                    num = 0
                if num > 4:
                    lobby_role = discord.utils.get(GLOBAL_GUILDS[guild_id].roles, name=f'Lobby')
                    id_message = await channel.send('{} {}'.format(lobby_role.mention, array[1]))
                    MESSAGE_MAPPING[message_id][0] = id_message.id
            elif len(array) > 1: # we have already created a message
                lobby_message = await after.channel.fetch_message(lobby_message_id)
                
                lobby_role = discord.utils.get(GLOBAL_GUILDS[guild_id].roles, name=f'Lobby')
                id_message = '{} {}'.format(lobby_role.mention, array[1])
                await lobby_message.edit(content=id_message)
        
        # now lets update status
        lobby_tuple = MESSAGE_MAPPING[message_id]
        lobby_tuple[1] = actual_status
    
    
@bot.event
async def on_message(message):
    channel = message.channel
    author = message.author
    if not author.bot or author.name != 'Arcade Watcher':
        return
    
    # check how recently we made a post
    guild_id = message.guild.id
    guild = GLOBAL_GUILDS[guild_id]
    # now go ahead and create a mapping, we want to wait until a lobby has 4 humans before broadcasting
    MESSAGE_MAPPING[message.id] = [None, 'lobby', channel.id, guild_id, datetime.now()] # message, status, channel_id, guild_id, creation
    
@tasks.loop(time=ALARM_TIME)    
async def update_messages():
    await bot.wait_until_ready()
    notification_message_mapping = {} # mapping of guild_id -> channel_id -> status = count
    for message_id in MESSAGE_MAPPING.keys():
        # now remove from message_mapping if old
        message = MESSAGE_MAPPING[message_id]
        if datetime.now() - message[4] > timedelta(hours = 24):
            del MESSAGE_MAPPING[message_id]
            continue
        
        guild_id = message[3]
        channel_id = message[2]
        status = message[1]
        if guild_id not in notification_message_mapping:
            notification_message_mapping[guild_id] = {}
        if channel_id not in notification_message_mapping[guild_id]:
            notification_message_mapping[guild_id][channel_id] = {}
        if status not in notification_message_mapping[guild_id][channel_id]:
            notification_message_mapping[guild_id][channel_id][status] = 0
        notification_message_mapping[guild_id][channel_id][status] += 1
        
        # now remove from message_mapping if old
        if datetime.now() - message[4] > timedelta(hours = 12):
            del MESSAGE_MAPPING[message_id]
    
    # print stats
    for guild_id in notification_message_mapping:
        for channel_id in notification_message_mapping[guild_id]:
            message = 'Lobby stats for the day:\n'
            for status in notification_message_mapping[guild_id][channel_id]:
                message += 'Status %s has %d entries.\n' % (status, notification_message_mapping[guild_id][channel_id][status])
            # now send message
            guild = GLOBAL_GUILDS[guild_id]
            channel = guild.get_channel(channel_id)
            await channel.send(message)
    
def get_start_end():
    dt = date.today()
    start = dt - timedelta(days=dt.weekday() + 1)
    end = start + timedelta(days=6)
    return start, end
    
def get_count(j, start):
    count = 0
    last = None
    for r in j['results']:
        datetime_object = datetime.strptime(r['createdAt'], '%Y-%m-%dT%H:%M:%S.%fZ').date()
        if r['status'] == 'started' and datetime_object > start:
            count += 1
        last = datetime_object
    return count, last > start

def get_this_week(start):
    r = requests.get(REQUEST_URL)
    if r.status_code != 200:
        print('error')
        return
    total_count = 0
    while True:
        j = r.json()
        count, cont = get_count(j, start)
        total_count += count
        if not cont:
            break
        next = j['page']['next']
        next_url = REQUEST_URL + '&after=' + next
        r = requests.get(next_url)
    return total_count
    
@tasks.loop(minutes=5)
async def update_channel():
    await bot.wait_until_ready()
    print('running update channel name')
    start, end = get_start_end()
    count = get_this_week(start)
    # now update the channel
    new_name = 'Games This Week: ' + str(count)
    for guild in GLOBAL_GUILDS:
        channel = discord.utils.find(lambda c: c.name.startswith('Games This Week'), GLOBAL_GUILDS[guild].channels)
        if channel and channel.name != new_name:
            await channel.edit(name=new_name)
            print('name different updating channel')
            
@bot.event
async def on_ready():    
    tasks = []
    for guild in bot.guilds:
        GLOBAL_GUILDS[guild.id] = guild
        tasks.append(setup_guild(guild))
    await asyncio.gather(*tasks)
    update_channel.start()
    update_messages.start()
    
asyncio.run(bot.run(TOKEN))