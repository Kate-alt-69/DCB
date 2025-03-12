import discord
from discord import app_commands
from discord.ext import commands
import os
from typing import Union
from discord.ext.commands import CooldownMapping
from datetime import datetime, timedelta
from KA import keep_alive  # Add this import
import asyncio
from discord.ui import Button, View

TOKEN = os.getenv("TOKEN_SM")
print("Debug: Available environment variables:", [k for k in os.environ.keys()])
print("Debug: Direct token access result:", bool(TOKEN))

if TOKEN:
    print("✅ Token Found Successfully✅")
    masked_token = TOKEN[:4] + "*" * (len(TOKEN) - 8) + TOKEN[-4:]
    print(f"Token check: {masked_token}")
else:
    print("\n❌ Token Was Not Found! Debug Info:")
    print("1. Environment Variable Name: TOKEN_SM")
    print("2. Available env vars:", [k for k in os.environ.keys() if k.startswith("TOKEN")])
    print("3. Try running these commands in the terminal:")
    print("   echo $TOKEN_SM")
    print("   printenv | grep TOKEN")
    raise ValueError("TOKEN_SM environment variable is not set or empty!")


class Bot(commands.Bot):
    def __init__(self):
        # Configure intents
        intents = discord.Intents.all()
        
        # Initialize dictionaries
        self.server_info = {}
        self.sticky_messages = {}
        self.sticky_cooldowns = {}
        self.sticky_last_sent = {}
        
        # Initialize bot
        super().__init__(
            command_prefix="SM!",
            intents=intents,
            activity=discord.Game(name="Server Manager"),
            status=discord.Status.online
        )
    
    async def reload_bot(self):
        """Reload the bot and sync commands"""
        try:
            await self.tree.sync()
            print("✅ Commands synced!")
            return True
        except Exception as e:
            print(f"❌ Error syncing commands: {e}")
            return False
    
    async def update_sticky_message(self, channel_id: int, message_id: int, content: Union[str, dict]):
        """Update sticky message in cache"""
        self.sticky_messages[channel_id] = {
            'message_id': message_id,
            'content': content,
            'is_embed': isinstance(content, dict)
        }

    async def setup_hook(self):
        """Called before the bot starts running"""
        await self.tree.sync()
        print("✅ Commands synced!")

    async def update_server_info(self, guild):
        """Update server information cache"""
        self.server_info[guild.id] = {
            'name': guild.name,
            'id': guild.id,
            'member_count': guild.member_count,
            'icon_url': guild.icon.url if guild.icon else None,
            'banner_url': guild.banner.url if guild.banner else None,
            'description': guild.description or "No description set",
            'owner': guild.owner,
            'created_at': guild.created_at,
            'roles': len(guild.roles),
            'channels': len(guild.channels),
            'boost_level': guild.premium_tier,
            'boost_count': guild.premium_subscription_count
        }

    async def on_command_error(self, ctx, error):
        """Handle traditional command errors"""
        if isinstance(error, commands.errors.CommandNotFound):
            await ctx.send("❌ Command not found!")
        elif isinstance(error, commands.errors.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command!")
        else:
            print(f"An error occurred: {str(error)}")
            await ctx.send("❌ An error occurred while executing the command!")

bot = Bot()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    channel_id = message.channel.id
    if channel_id in bot.sticky_messages:
        # Check cooldown
        now = datetime.utcnow()
        last_sent = bot.sticky_last_sent.get(channel_id)
        cooldown = bot.sticky_cooldowns.get(channel_id, 1)
        
        if last_sent and (now - last_sent).total_seconds() < 0.005:  # 5ms check
            return  # Still on cooldown
            
        sticky_data = bot.sticky_messages[channel_id]
        
        # Delete ALL previous sticky messages to prevent duplication
        async for old_message in message.channel.history(limit=50):  # Increased search limit
            if old_message.author == bot.user and (
                old_message.id == sticky_data.get('message_id') or
                (old_message.embeds and sticky_data.get('is_embed')) or
                (not old_message.embeds and not sticky_data.get('is_embed'))
            ):
                try:
                    await old_message.delete()
                except discord.NotFound:
                    pass
        
        # Wait briefly to ensure message order
        await asyncio.sleep(0.1)
        
        # Send new sticky message
        if sticky_data.get('is_embed', False):
            content = sticky_data['content']
            embed = discord.Embed(
                title=content.get('title', 'Sticky Message'),
                description=content.get('description'),
                color=getattr(discord.Color, content.get('color', 'blue'))()
            )
            embed.set_footer(text=f"📌 Sticky message • {message.guild.name}")
            embed.timestamp = discord.utils.utcnow()
            new_sticky = await message.channel.send(embed=embed)
        else:
            new_sticky = await message.channel.send(sticky_data['content'])
        
        # Update tracking
        bot.sticky_last_sent[channel_id] = now
        await bot.update_sticky_message(
            channel_id,
            new_sticky.id,
            sticky_data['content']
        )

# Error handler for slash commands
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handle slash command errors"""
    try:
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏰ Command on cooldown. Try again in {error.retry_after:.2f}s",
                ephemeral=True
            )
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "🔒 You don't have permission to use this command!",
                ephemeral=True
            )
        else:
            print(f"Slash command error: {str(error)}")
            await interaction.response.send_message(
                "❌ An error occurred while executing this command!",
                ephemeral=True
            )
    except Exception as e:
        print(f"Error in error handler: {str(e)}")

@bot.tree.command(name="ping", description="Check bot's ping")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! {latency}ms")

@bot.tree.command(name="about", description="About Of The Bot")
async def embed(interaction: discord.Interaction):
    try:
        # Create embed first
        embed = discord.Embed(
            title="Welcome to Server Manager!",
            description="A powerful Discord bot for server management, and Creating Custom Message's",
            color=discord.Color.purple()
        )
        
        # Add fields to the embed
        embed.add_field(
            name="🛠️ Features", 
            value="• Server Management\n• Custom Commands\n• Moderation Tools", 
            inline=False
        )
        
        # Add author information
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        # Add footer
        embed.set_footer(
            text=f"Requested by {interaction.user.name}",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        
        # Add timestamp
        embed.timestamp = discord.utils.utcnow()
        
        # Send the embed
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        print(f"Error in embed command: {e}")
        await interaction.response.send_message(
            "❌ Failed to create embed!",
            ephemeral=True
        )

@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="The member to kick", reason="Reason for kicking")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    try:
        # Update server info
        await bot.update_server_info(interaction.guild)
        server_name = bot.server_info[interaction.guild.id]['name']
        
        await member.kick(reason=reason)
        await interaction.response.send_message(
            f"✅ Successfully kicked {member.mention} from {server_name}\n"
            f"Reason: {reason or 'No reason provided'}",
            ephemeral=True
        )
    except Exception as e:
        print(f"Error in kick command: {e}")
        await interaction.response.send_message("❌ Failed to kick member!", ephemeral=True)

@bot.tree.command(name="sticky", description="Create or remove sticky messages")
@app_commands.describe(
    action="Choose create, create-embed, or remove",
    title="Title for embed (only for create-embed)",
    description="Message content or embed description",
    color="Color for embed (optional)",
    cooldown="Cooldown in seconds between sticky messages(default: 1)"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="create", value="create"),
        app_commands.Choice(name="create-embed", value="create-embed"),
        app_commands.Choice(name="remove", value="remove")
    ],
    color=[
        app_commands.Choice(name="blue", value="blue"),
        app_commands.Choice(name="red", value="red"),
        app_commands.Choice(name="green", value="green"),
        app_commands.Choice(name="purple", value="purple")
    ]
)
@app_commands.default_permissions(manage_messages=True)
async def sticky(
    interaction: discord.Interaction,
    action: str,
    description: str = None,
    title: str = None,
    color: str = "blue",
    cooldown: int = 1
):
    try:
        channel_id = interaction.channel.id
        
        if action == "create" or action == "create-embed":
            if not description:
                await interaction.response.send_message(
                    "❌ Please provide a message!", 
                    ephemeral=True
                )
                return
            
            # Store cooldown
            bot.sticky_cooldowns[channel_id] = cooldown
            bot.sticky_last_sent[channel_id] = datetime.utcnow()
            
            if action == "create":
                sticky_msg = await interaction.channel.send(description)
                await bot.update_sticky_message(channel_id, sticky_msg.id, description)
            else:  # create-embed
                colors = {
                    "blue": discord.Color.blue(),
                    "red": discord.Color.red(),
                    "green": discord.Color.green(),
                    "purple": discord.Color.purple()
                }
                
                embed = discord.Embed(
                    title=title or "Sticky Message",
                    description=description,
                    color=colors.get(color, discord.Color.blue())
                )
                embed.set_footer(text=f"Sticky message • {interaction.guild.name} • Cooldown: {cooldown}s")
                embed.timestamp = discord.utils.utcnow()
                
                sticky_msg = await interaction.channel.send(embed=embed)
                await bot.update_sticky_message(
                    channel_id,
                    sticky_msg.id,
                    {"type": "embed", "title": title, "description": description, "color": color}
                )
            
            await interaction.response.send_message(
                f"✅ Sticky message created with {cooldown}s cooldown!", 
                ephemeral=True
            )
            
        elif action == "remove":
            if channel_id not in bot.sticky_messages:
                await interaction.response.send_message(
                    "❌ No sticky message here!", 
                    ephemeral=True
                )
                return
            
            try:
                sticky_msg = await interaction.channel.fetch_message(
                    bot.sticky_messages[channel_id]['message_id']
                )
                await sticky_msg.delete()
            except discord.NotFound:
                pass
            
            # Clean up cooldown data
            del bot.sticky_messages[channel_id]
            bot.sticky_cooldowns.pop(channel_id, None)
            bot.sticky_last_sent.pop(channel_id, None)
            
            await interaction.response.send_message(
                "✅ Sticky message removed!", 
                ephemeral=True
            )
            
    except Exception as e:
        print(f"Error in sticky command: {e}")
        await interaction.response.send_message(
            "❌ Failed to manage sticky message!", 
            ephemeral=True
        )

@bot.tree.command(name="restart", description="Restart and reload the bot (Admin only)")
@app_commands.default_permissions(administrator=True)
async def restart(interaction: discord.Interaction):
    try:
        await interaction.response.send_message("🔄 Restarting bot...", ephemeral=True)
        
        # Reload bot
        success = await bot.reload_bot()
        
        if success:
            await interaction.edit_original_response(
                content="✅ Bot restarted and commands resynced successfully!"
            )
            
            # Optional: Update bot's status/activity
            await bot.change_presence(
                activity=discord.Game(name="Server Manager"),
                status=discord.Status.online
            )
        else:
            await interaction.edit_original_response(
                content="❌ Failed to restart bot. Check console for errors."
            )
    except Exception as e:
        print(f"Error in restart command: {e}")
        await interaction.edit_original_response(
            content="❌ An error occurred while restarting the bot!"
        )

class EmbedView(View):
    def __init__(self):
        super().__init__(timeout=60)  # 60 seconds timeout
        
    @discord.ui.button(label="Main Menu", style=discord.ButtonStyle.blurple, custom_id="main_menu")
    async def main_menu_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="Embed Creator - Main Menu",
            description="Select an option below to customize your embed:",
            color=discord.Color.blue()
        )
        embed.add_field(name="🎨 Colors", value="Change embed color", inline=True)
        embed.add_field(name="📝 Content", value="Edit title and description", inline=True)
        embed.add_field(name="🖼️ Images", value="Add images or thumbnails", inline=True)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Colors", style=discord.ButtonStyle.green, custom_id="colors")
    async def colors_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="Embed Creator - Colors",
            description="Available colors:\n\n"
                       "🔵 Blue\n"
                       "🔴 Red\n"
                       "🟢 Green\n"
                       "🟣 Purple\n"
                       "⚫ Black\n"
                       "⚪ White",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Content", style=discord.ButtonStyle.gray, custom_id="content")
    async def content_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="Embed Creator - Content",
            description="Content options:\n\n"
                       "📌 Title\n"
                       "📄 Description\n"
                       "📋 Fields\n"
                       "👤 Author\n"
                       "👣 Footer",
            color=discord.Color.greyple()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Images", style=discord.ButtonStyle.red, custom_id="images")
    async def images_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="Embed Creator - Images",
            description="Image options:\n\n"
                       "🖼️ Main Image\n"
                       "🔳 Thumbnail\n"
                       "🎴 Author Icon\n"
                       "🏷️ Footer Icon",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="embed_creator", description="Create a custom embed message")
@app_commands.default_permissions(manage_messages=True)
async def embed_creator(interaction: discord.Interaction):
    """Create a custom embed using an interactive menu"""
    try:
        embed = discord.Embed(
            title="Embed Creator - Main Menu",
            description="Select an option below to customize your embed:",
            color=discord.Color.blue()
        )
        embed.add_field(name="🎨 Colors", value="Change embed color", inline=True)
        embed.add_field(name="📝 Content", value="Edit title and description", inline=True)
        embed.add_field(name="🖼️ Images", value="Add images or thumbnails", inline=True)
        
        view = EmbedView()
        await interaction.response.send_message(embed=embed, view=view)
        
    except Exception as e:
        print(f"Error in embed_creator command: {e}")
        await interaction.response.send_message(
            "❌ Failed to create embed creator!",
            ephemeral=True
        )

if __name__ == "__main__":
    try:
        keep_alive()  # Start the web server
        print("✅ Web server started!")
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")