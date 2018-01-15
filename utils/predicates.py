import discord
from discord.ext import commands

def is_private():
    def predicate(ctx):
        return isinstance(ctx.channel, discord.channel.DMChannel)
    return commands.check(predicate)

def not_private():
    def predicate(ctx):
        return isinstance(ctx.channel, discord.channel.TextChannel)
    return commands.check(predicate)