import discord
from discord.ext import commands
from discord_slash import SlashCommand, SlashContext
from discord_slash.model import ContextMenuType
import re

import os
from dotenv import load_dotenv

import asyncio

from datetime import datetime, timedelta

load_dotenv()



TOKEN = os.getenv("DISCORD_TOKEN")

description = '''Island Defense Bot'''

intents = discord.Intents.default()
GLOBAL_GUILDS = {}
MESSAGE_MAPPING = {} # mapping of lobby bot message id to island defense bot message

ALARM_TIME = '03:30'

bot = commands.Bot(command_prefix='/', description=description, intents=intents)
slash = SlashCommand(bot, sync_commands=True)
# , guild_ids=[455844188164980737]
@slash.slash(name="armour", description='Calculate the damage reduction')#, target=ContextMenuType.MESSAGE)
async def armour(ctx: SlashContext, armour,):
    try:
        i = int(armour)
    except ValueError:
        await ctx.send('You can only type a number')
        return
    v = (i*.06)/(1+0.06*i)
    await ctx.send('Damage reduction for armour %d percentage %.2f' % (i, v))
    
    
async def create_roles_for_guild(guild):
    private_house_role = discord.utils.get(guild.roles, name=f'island_defense_lobby_broadcast_role')
    if private_house_role is None:
        private_house_role = await guild.create_role(name=f'island_defense_lobby_broadcast_role')

async def setup_guild(guild):
    pass
    #await create_roles_for_guild(guild) # create roles for guild 

@bot.event
async def on_guild_join(guild):
    GLOBAL_GUILDS[guild.id] = guild
    await setup_guild(guild)

@bot.event
async def on_ready():    
    tasks = []
    for guild in bot.guilds:
        GLOBAL_GUILDS[guild.id] = guild
        tasks.append(setup_guild(guild))
    await asyncio.gather(*tasks)
    '''
    guild = GLOBAL_GUILDS[519347399374798848]
    for c in guild.channels:
        if c.id == 870846403876892722:
            m = await c.fetch_message(945885757535584327)
            if len(m.embeds[0].fields) > 1:
                print(m.embeds[0].fields[0].value)
                print(m.embeds[0].fields[0].value.strip())
                status = m.embeds[0].fields[0].value.strip()
                print(re.sub('[^A-Z]', '', status))
                '''
    
        
        
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
        
async def update_messages():
    await bot.wait_until_ready()
    while not bot.is_closed():
        diff = 60 
        now = datetime.strftime(datetime.now(), '%H:%M')
        if now == ALARM_TIME:
            # do work
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
        else:
            diff = (datetime.strptime(ALARM_TIME, '%H:%M') - datetime.strptime(now, '%H:%M')).total_seconds()
        if diff < 0:
            diff = 86400 + diff
        print('waiting %d secodns to sleep' % diff)
        await asyncio.sleep(diff)
    
    
bot.loop.create_task(update_messages())
bot.run(TOKEN)