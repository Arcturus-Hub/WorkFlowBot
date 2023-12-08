import os
import sys
import random
import discord
from discord.ext import commands
from discord import app_commands

from webserver import keep_alive

import json

# open the jobs.json file and load it into the jobs dictonary
file = open('jobs.json', 'r')
jobs = json.load(file)
file.close()


# dumps the jobs into jobs.json
def dumpJobs():
  file = open('jobs.json', 'w')
  json.dump(jobs, file, indent=4)
  file.close()


# init bot and its values
description = "A bot for managing jobs in the Arcturus Game Dev Server"

bot = commands.Bot(command_prefix = '/',
                   description = description,
                   intents = discord.Intents.all())

bot.remove_command('help')

@bot.event
async def on_ready():
  # this is not good practice for a bot that is in multiple guildes
  synced = await bot.tree.sync()

  print(
      f"Bot logged in as {bot.user}\nSynced {len(synced)} commands into the guild"
  )


quitMsg = ["exit", "quit", "cancel"]
bannedNameSymbols = [
    '\\', '/', '\n', '*', '?', '"', '<', '>', '|', '!', '$', '+', '=', ',',
    '.', ';'
]
bannedDescSymbols = ['\\', '*', '"', '<', '>', '|', '$', '+', '=']

createMsgs = []


async def cleanCreateMsgs():
  for msg in createMsgs:
    await msg.delete()

  createMsgs.clear()


async def inputCheck(ctx, bannedSymbols, quitMsg):
  msg = await bot.wait_for(
      'message',
      check = lambda message: message.author == ctx.author and message != ctx)

  createMsgs.append(msg)

  if (msg.content.lower() in quitMsg):
    await ctx.send("Quitting...")
    await cleanCreateMsgs()
    return None

  for ch in msg.content:
    for sym in bannedSymbols:
      if (ch == sym):
        createMsgs.append(
            await ctx.send(f"You can't use '{sym}' in this field! Try again:"))
        return await inputCheck(ctx, bannedSymbols, quitMsg)

  return msg.content


async def get_channel(ctx):
  channel_str = await inputCheck(ctx, [], quitMsg)
  if (channel_str is None):
    return None

  if (len(channel_str) < 4):
    createMsgs.append(await ctx.send("Error processing input! Try again"))
    return await get_channel(ctx)

  try:
    channel_id = int(str(channel_str)[2:-1])
  except ValueError:
    createMsgs.append(await ctx.send("Error processing input! Try again"))
    return await get_channel(ctx)

  channel = ctx.guild.get_channel(channel_id)

  if (channel is None):
    createMsgs.append(await ctx.send("Channel not found! Try again"))
    return await get_channel(ctx)

  return channel


@bot.hybrid_command(name = "create",
                    description = "Used by a Team Leader to create a new job")
@commands.has_permissions(administrator=True)
async def create(ctx):
  createMsgs.append(
      await
      ctx.send("Creating a new job...\nPlease enter the name of the job:\n"))

  jobData = {}
  jobData["taken"] = False

  jobData["name"] = await inputCheck(ctx, bannedNameSymbols, quitMsg)
  if jobData["name"] is None:
    return

  createMsgs.append(await ctx.send("Please enter the description of the job:"))

  jobData["description"] = await inputCheck(ctx, bannedDescSymbols, quitMsg)
  if jobData["description"] is None:
    return

  createMsgs.append(
      await ctx.send("Please enter the due data in MM/DD/YYYY format:"))

  jobData["dueDate"] = await inputCheck(ctx, bannedDescSymbols, quitMsg)
  if jobData["dueDate"] is None:
    return

  createMsgs.append(await ctx.send("How many points does this job offer?"))

  jobData["points"] = None
  while jobData["points"] is None:
    try:
      points_str = await inputCheck(ctx, bannedDescSymbols, quitMsg)
      if (points_str is None):
        return

      jobData["points"] = int(str(points_str))

    except ValueError:
      createMsgs.append(await ctx.send("Error processing input! Try again"))
      jobData["points"] = None

  role = None
  while (role is None):
    createMsgs.append(await ctx.send("Please enter the role for the job:"))

    roleName = await inputCheck(ctx, bannedNameSymbols, quitMsg)
    if (roleName is None):
      return

    # If the user wants to quit during this part of the process
    if (roleName.lower() in quitMsg):
      ctx.send("Quitting...")
      await cleanCreateMsgs()
      return

    # try to find the role by the name
    role = discord.utils.get(ctx.guild.roles, name=roleName)

    # send error when the role isn't found
    if (role is None):
      createMsgs.append(await ctx.send(f"Role {roleName}, not found"))

  createMsgs.append(
      await ctx.send("Please enter the channel for this job to be posted in:"))

  channel = await get_channel(ctx)
  if (channel is None):
    return

  createMsgs.append(await ctx.send(
      "Please enter the archive channel for this job to be posted in:"))

  achannel = await get_channel(ctx)
  if (achannel is None):
    return

  # generate the code
  code = None
  while code is None:
    code = f"{random.randint(0, 9)}{random.randint(0, 9)}{random.randint(0, 9)}"

    if code in jobs:
      code = None

  # add the jobData to the job dict and dump it to the .JSON file
  embed = discord.Embed(title=jobData["name"],
                        description = jobData["description"],
                        color = 0x00ff00)

  embed.add_field(name = "Due Date", value=jobData["dueDate"])

  embed.add_field(name = "Role", value=role.mention)

  embed.add_field(name = "Points", value=jobData["points"])

  embed.set_footer(text=f"use /claim {code} to accept this job")

  msg = await channel.send(embed = embed)
  await achannel.send(embed = embed)

  msg2 = await channel.send(f"|| {role.mention} ||")

  jobData["channel"] = channel.id
  jobData["msg"] = [msg.id, msg2.id]

  jobs[code] = jobData
  dumpJobs()

  await ctx.send("Job created!")
  await cleanCreateMsgs()


@bot.hybrid_command(name = "claim", description = "claim a job")
async def claim(ctx, job_id):
  if (job_id not in jobs):
    await ctx.send(f"Job with id {job_id} not found")
    return

  if (jobs[job_id]["taken"]):
    await ctx.send(
        f"Job with id {job_id} is already claimed. If this is a mistake, you may need to ask the user to unclaim it."
    )
    return

  jobs[job_id]["taken"] = True
  jobs[job_id]["user"] = ctx.author.id

  if (str(ctx.author.id) not in jobs):
    jobs[str(ctx.author.id)] = {}
    jobs[str(ctx.author.id)]["jobs"] = []
    jobs[str(ctx.author.id)]["points"] = 0

  jobs[str(ctx.author.id)]["jobs"].append(
      f"{jobs[job_id]['name']} | points : {jobs[job_id]['points']}")

  dumpJobs()

  await ctx.send(f"Job {job_id} claimed")


@bot.hybrid_command(name = "unclaim", description = "unclaim a job")
async def unclaim(ctx, job_id):
  if (job_id not in jobs):
    await ctx.send(f"Job with id {job_id} not found")
    return

  if (not jobs[job_id]["taken"]):
    await ctx.send(f"Job with id {job_id} is not currently claimed.")
    return

  if (jobs[job_id]["user"] != ctx.author.id):
    await ctx.send("You are not the user who claimed this job.")
    return

  for job in jobs[str(ctx.author.id)]["jobs"]:
    if (job == f"{jobs[job_id]['name']} | points : {jobs[job_id]['points']}"):
      jobs[str(ctx.author.id)]["jobs"].remove(job)
      print("job removed")

  del jobs[job_id]["user"]
  jobs[job_id]["taken"] = False
  dumpJobs()

  await ctx.send(f"Job {job_id} unclaimed")


@bot.hybrid_command(name = "delete",
                    description = "Used by a Team Leader to delete a job")
@commands.has_permissions(administrator=True)
async def delete(ctx, job_id):
  if (job_id not in jobs):
    await ctx.send(f"Job with id {job_id} not found")
    return

  channel = ctx.guild.get_channel(jobs[job_id]["channel"])

  for msg in jobs[job_id]["msg"]:
    msg = await channel.fetch_message(msg)
    await msg.delete()

  del jobs[job_id]
  dumpJobs()
  await ctx.send(f"Job {job_id} deleted")


@bot.hybrid_command(name = "status", description = "Shows the status of a job")
async def status(ctx, job_id):
  if (job_id not in jobs):
    await ctx.send(
        f"Job with id {job_id} not found or has been deleted or finished")
    return

  if (jobs[job_id]["taken"]):
    await ctx.send(f"The job with the id {job_id} is taken")
    return

  await ctx.send(f"The job with the id {job_id} is not taken")


@bot.hybrid_command(
    name = "user",
    description = "Get info on a specific user (eg. jobs or points)")
async def user(ctx, member: discord.Member = None):
  if (member is None or str(member.id) not in jobs):
    await ctx.send("User not found")
    return

  description = ""

  embed = discord.Embed(title=member.name,
                        description = description,
                        color = 0xf0f000)

  embed.add_field(name = "Points", value=jobs[str(member.id)]["points"])
  embed.set_thumbnail(url=member.avatar)

  for job in jobs[str(member.id)]["jobs"]:
    embed.add_field(name = "", value = "", inline = False)
    embed.add_field(name = job, value = "")

  await ctx.send(embed = embed)


@bot.hybrid_command(
    name = "finish",
    description = "Used by a Team Leader to mark a job as finished")
@commands.has_permissions(administrator=True)
async def finish(ctx, job_id):
  if (job_id not in jobs):
    await ctx.send(f"Job with id {job_id} not found")
    return

  if "points" not in jobs[job_id]:
    jobs[job_id]["points"] = 1

  jobs[str(jobs[job_id]["user"])]["points"] += jobs[job_id]["points"]

  await delete(ctx, job_id)


@bot.hybrid_command(
    name = "give_points",
    description = "Used by a Team Leader to take away points from a user")
@commands.has_permissions(administrator=True)
async def give_points(ctx, points: int, member: discord.Member = None):
  if (member is None or str(member.id) not in jobs):
    await ctx.send("User not found")
    return

  jobs[str(member.id)]["points"] += points
  jobs[str(member.id)]["jobs"].append(f"MANAGER BONUS | Points: {points}")
  dumpJobs()

  if (points > 0):
    await ctx.send(f"{points} points given to {member.name}")

  if (points < 0):
    await ctx.send(f"{-points} points taken away from {member.name}")


@bot.hybrid_command(
    name = "remove_points",
    description = "Used by a Team Leader to give points to a user")
@commands.has_permissions(administrator=True)
async def remove_points(ctx, points: int, member: discord.Member = None):
  await give_points(ctx, -points, member)


@bot.hybrid_command(name = "help", description = "Sends help message")
async def help(ctx):
  embed = discord.Embed(title = "Help",
                        description = "Command list",
                        color = 0x0000ff)

  embed.add_field(name = "/help", value = "Shows this message")

  embed.add_field(
      name = "/create",
      value=
      "Used by a Team Leader to create a new job with the given a job based on given args",
      inline = False)

  embed.add_field(name = "/claim <job_id>", value = "Claims a job", inline = False)

  embed.add_field(name = "/unclaim <job_id>",
                  value = "Unclaims a job",
                  inline = False)

  embed.add_field(name = "/delete <job_id>",
                  value = "Deletes a job from the list",
                  inline = False)

  embed.add_field(
      name = "/status <job_id>",
      value = "Gets the status of a job (claimed/unclaimed, finished/unfinished)",
      inline = False)

  embed.add_field(name = "/user <user>",
                  value = "Shows the jobs a specific user has claimed",
                  inline = False)

  embed.add_field(
      name = "/finish <job_id>",
      value=
      "Used by a Team Leader to mark a job as completed and give them a point",
      inline = False)

  embed.add_field(name = "/give_points <points> <user>",
                  value = "Used by a Team Leader to give points to a user",
                  inline = False)

  embed.add_field(
      name = "/remove_points <points> <user>",
      value = "Used by a Team Leader to take away points from a user",
      inline = False)

  embed.add_field(name = "/idea <name> <desc>", value = "creates an idea vote")
  await ctx.send(embed = embed)


@bot.hybrid_command(name = "idea", description = "creates an idea vote")
async def idea(ctx, suggestion: str, suggestion_descriptor: str):
  embed = discord.Embed(title=f"{suggestion}",
                        description = f"{suggestion_descriptor}",
                        color = 0xff641c)

  embed.set_footer(text = "React to vote")

  message = await ctx.send(embed = embed)
  await message.add_reaction("\U00002705")
  await message.add_reaction("\U0000274C")

@bot.hybrid_command(name = "announce", description = "announces something")
async def announce(ctx, message: str, image_link: str):
  embed = discord.Embed(title = "ANNOUNCEMENT",
                        description = f"{message}",
                        color = 0x00ff00)

  embed.set_image(url = image_link)

  await ctx.send(embed = embed)

@bot.command()
@commands.guild_only()
async def sync(ctx):
  synced = await ctx.bot.tree.sync()
  await ctx.send(f"Synced {len(synced)} commands into the guild")


keep_alive()

token = os.environ['DISCORD_BOT_SECRET']
bot.run(token)

if (len(sys.argv) > 1 and sys.argv[1] == "github"):
    exit()