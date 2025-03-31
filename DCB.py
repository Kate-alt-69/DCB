import discord
from discord import app_commands
from discord.ext import commands
import os
from typing import Union, Dict
from discord.ext.commands import CooldownMapping
from datetime import datetime, timedelta
from KA import keep_alive  # Add this import
import asyncio
from discord.ui import Button, View
import json
from pathlib import Path

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
        intents = discord.Intents.default()
        intents.message_content = True
        
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
        
        self.data_folder = Path("data")
        self.data_folder.mkdir(exist_ok=True)
        self.sticky_file = self.data_folder / "sticky_messages.json"
        self.load_sticky_messages()
    
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

    def save_sticky_messages(self):
        """Save sticky messages to file"""
        try:
            data = {
                str(channel_id): {
                    'message_id': info['message_id'],
                    'content': info['content'],
                    'name': info.get('name', 'Unnamed'),
                    'is_embed': info.get('is_embed', False)
                }
                for channel_id, info in self.sticky_messages.items()
            }
            
            with open(self.sticky_file, 'w') as f:
                json.dump(data, f, indent=4)
                
            print("✅ Sticky messages saved!")
        except Exception as e:
            print(f"❌ Error saving sticky messages: {e}")

    def load_sticky_messages(self):
        """Load sticky messages from file"""
        try:
            if self.sticky_file.exists():
                with open(self.sticky_file, 'r') as f:
                    data = json.load(f)
                
                self.sticky_messages = {
                    int(channel_id): info
                    for channel_id, info in data.items()
                }
                print("✅ Sticky messages loaded!")
            else:
                self.sticky_messages = {}
                print("📝 No sticky messages file found, starting fresh!")
        except Exception as e:
            print(f"❌ Error loading sticky messages: {e}")
            self.sticky_messages = {}

bot = Bot()
bot.mod_roles: Dict[int, int] = {}  # guild_id: role_id

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    channel_id = message.channel.id
    if channel_id in bot.sticky_messages:
        # Initialize message counter if not exists
        if 'msg_count' not in bot.sticky_messages[channel_id]:
            bot.sticky_messages[channel_id]['msg_count'] = 0
        
        # Increment message counter
        bot.sticky_messages[channel_id]['msg_count'] += 1
        
        # Check if we've reached 2 non-bot messages
        if bot.sticky_messages[channel_id]['msg_count'] >= 2:
            sticky_data = bot.sticky_messages[channel_id]
            
            try:
                # Delete previous sticky message if it exists
                if 'message_id' in sticky_data:
                    try:
                        old_message = await message.channel.fetch_message(sticky_data['message_id'])
                        await old_message.delete()
                    except discord.NotFound:
                        pass
                
                # Send new sticky message
                if sticky_data.get('is_embed'):
                    content = sticky_data['content']
                    embed = discord.Embed(
                        title=content.get('title', 'Sticky Message'),
                        description=content.get('description'),
                        color=getattr(discord.Color, content.get('color', 'blue'))()
                    )
                    embed.set_footer(text=f"📌 {sticky_data['name']} • {message.guild.name}")
                    embed.timestamp = discord.utils.utcnow()
                    new_sticky = await message.channel.send(embed=embed)
                else:
                    new_sticky = await message.channel.send(sticky_data['content'])
                
                # Update message ID and reset counter
                bot.sticky_messages[channel_id]['message_id'] = new_sticky.id
                bot.sticky_messages[channel_id]['msg_count'] = 0
                bot.save_sticky_messages()
                
            except Exception as e:
                print(f"Error updating sticky message: {e}")
            
    await bot.process_commands(message)

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

# Update sticky command to include name parameter
@bot.tree.command(name="sticky", description="Create a sticky message")
@app_commands.describe(
    name="Name for the sticky message",
    action="Choose create or create-embed",
    title="Title for embed (only for create-embed)",
    description="Message content or embed description",
    color="Color for embed (optional)",
    cooldown="Cooldown in seconds between sticky messages(default: 1)"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="create", value="create"),
        app_commands.Choice(name="create-embed", value="create-embed")
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
    name: str,
    action: str,
    description: str = None,
    title: str = None,
    color: str = "blue",
    cooldown: int = 1
):
    try:
        channel_id = interaction.channel.id
        
        # Check for existing sticky message
        if channel_id in bot.sticky_messages:
            await interaction.response.send_message(
                "❌ This channel already has a sticky message! Remove it first.",
                ephemeral=True
            )
            return
            
        if not description:
            await interaction.response.send_message(
                "❌ Please provide a message!",
                ephemeral=True
            )
            return

        # Delete any existing messages from the bot in channel
        async for old_message in interaction.channel.history(limit=50):
            if old_message.author == bot.user:
                try:
                    await old_message.delete()
                except discord.NotFound:
                    pass

        await interaction.response.defer(ephemeral=True)

        # Create and send the sticky message
        if action == "create":
            sticky_msg = await interaction.channel.send(description)
            sticky_data = {
                'message_id': sticky_msg.id,
                'content': description,
                'name': name,
                'is_embed': False
            }
        else:  # create-embed
            embed = discord.Embed(
                title=title or "Sticky Message",
                description=description,
                color=getattr(discord.Color, color)()
            )
            embed.set_footer(text=f"📌 {name} • {interaction.guild.name}")
            embed.timestamp = discord.utils.utcnow()
            sticky_msg = await interaction.channel.send(embed=embed)
            sticky_data = {
                'message_id': sticky_msg.id,
                'content': {
                    'title': title,
                    'description': description,
                    'color': color
                },
                'name': name,
                'is_embed': True
            }
        # Update bot's sticky message tracking
        bot.sticky_messages[channel_id] = sticky_data
        bot.sticky_cooldowns[channel_id] = cooldown
        bot.save_sticky_messages()
        bot.sticky_last_sent[channel_id] = datetime.utcnow()

        await interaction.followup.send(
            f"✅ Sticky message '{name}' created with {cooldown}s cooldown!",
            ephemeral=True
        )

    except Exception as e:
        print(f"Error in sticky command: {e}")
        await interaction.followup.send(
            "❌ Failed to create sticky message!",
            ephemeral=True
        )

# Add new stickremove command
@bot.tree.command(name="stickremove", description="Remove a sticky message by name")
@app_commands.describe(name="Name of the sticky message to remove")
@app_commands.default_permissions(manage_messages=True)
async def stickremove(interaction: discord.Interaction, name: str):
    try:
        # Show all sticky messages first
        embed = discord.Embed(
            title="Active Sticky Messages",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        if not bot.sticky_messages:
            embed.description = "No sticky messages are set in any channel"
        else:
            for channel_id, sticky in bot.sticky_messages.items():
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    content = sticky['content']
                    if isinstance(content, dict):
                        message_preview = content.get('description', '')[:50]
                    else:
                        message_preview = str(content)[:50]
                    embed.add_field(
                        name=f"#{channel.name} - {sticky.get('name', 'Unnamed')}",
                        value=f"{message_preview}...",
                        inline=False
                    )

        # Handle removal if name was provided
        channel_id = interaction.channel.id
        if channel_id in bot.sticky_messages:
            sticky_data = bot.sticky_messages[channel_id]
            if sticky_data.get('name') != name:
                await interaction.response.send_message(
                    embed=embed,
                    content=f"❌ No sticky message found with name '{name}'!",
                    ephemeral=True
                )
                return

            try:
                sticky_msg = await interaction.channel.fetch_message(sticky_data['message_id'])
                await sticky_msg.delete()
            except discord.NotFound:
                pass

            # Clean up data
            del bot.sticky_messages[channel_id]
            bot.sticky_last_sent.pop(channel_id, None)
            bot.sticky_cooldowns.pop(channel_id, None)
            bot.save_sticky_messages()

            embed.add_field(
                name="✅ Action Taken",
                value=f"Removed sticky message '{name}' from #{interaction.channel.name}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        print(f"Error in stickremove command: {e}")
        await interaction.response.send_message("❌ Failed to remove sticky message!", ephemeral=True)

@bot.tree.command(name="restart", description="Restart and reload the bot (Admin only)")
async def restart(interaction: discord.Interaction):
    await interaction.response.send_message("🔄 Restarting bot...", ephemeral=True)
    success = await bot.reload_bot()
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="Server Manager")
    )
    if success:
        await interaction.edit_original_response(
            content="✅ Bot restarted and commands resynced successfully!"
        )
    else:
        await interaction.edit_original_response(
            content="❌ Failed to restart bot. Check console for errors."
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
        embed.add_field(name="📝 Content", value="Edit title and description", inline=True)
        embed.add_field(name="🖼️ Images", value="Add images or thumbnails", inline=True)
        embed.add_field(name="🎨 Colors", value="Change embed color", inline=True)
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

class EmbedEditor(View):
    def __init__(self, original_embed: discord.Embed):
        super().__init__(timeout=300)  # 5 minute timeout
        self.embed = original_embed
        self.fields = []

    @discord.ui.button(label="Edit Title", style=discord.ButtonStyle.blurple)
    async def edit_title(self, interaction: discord.Interaction, button: Button):
        modal = EmbedModal(title="Edit Title", label="New Title")
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.value:
            self.embed.title = modal.value
            await interaction.message.edit(embed=self.embed)

    @discord.ui.button(label="Edit Description", style=discord.ButtonStyle.blurple)
    async def edit_description(self, interaction: discord.Interaction, button: Button):
        modal = EmbedModal(title="Edit Description", label="New Description")
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.value:
            self.embed.description = modal.value
            await interaction.message.edit(embed=self.embed)

    @discord.ui.button(label="Add Field", style=discord.ButtonStyle.green)
    async def add_field(self, interaction: discord.Interaction, button: Button):
        modal = FieldModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.name and modal.value:
            self.embed.add_field(name=modal.name, value=modal.value, inline=True)
            await interaction.message.edit(embed=self.embed)

    @discord.ui.button(label="Send Embed", style=discord.ButtonStyle.red)
    async def send_embed(self, interaction: discord.Interaction, button: Button):
        channel = interaction.channel
        await channel.send(embed=self.embed)
        await interaction.response.send_message("✅ Embed sent!", ephemeral=True)
        self.stop()

class EmbedModal(discord.ui.Modal):
    def __init__(self, title: str, label: str):
        super().__init__(title=title)
        self.value = None
        self.text = discord.ui.TextInput(
            label=label,
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000
        )
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction):
        self.value = self.text.value
        await interaction.response.send_message("✅ Updated!", ephemeral=True)

class FieldModal(discord.ui.Modal, title="Add Field"):
    field_name = discord.ui.TextInput(
        label="Field Name",
        required=True,
        max_length=256
    )
    field_value = discord.ui.TextInput(
        label="Field Value",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1024
    )

    def __init__(self):
        super().__init__()
        self.name = None
        self.value = None

    async def on_submit(self, interaction: discord.Interaction):
        self.name = self.field_name.value
        self.value = self.field_value.value
        await interaction.response.send_message("✅ Field added!", ephemeral=True)

# Update embed_creator command
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
        # Make the message ephemeral (private)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    except Exception as e:
        print(f"Error in embed_creator command: {e}")
        await interaction.response.send_message("❌ Failed to create embed creator!", ephemeral=True)

# delete message command
@bot.tree.command(name="deletemessage", description="Delete a specified number of messages")
@app_commands.describe(amount="Number of messages to delete (1-200)")
@commands.cooldown(1, 5, commands.BucketType.channel)
async def deletemessage(interaction: discord.Interaction, amount: int):
    """Delete a specified number of messages"""
    try:
        if not await has_mod_role(interaction):
            await interaction.response.send_message(
                "🔒 You need moderator role to use this command!",
                ephemeral=True
            )
            return

        if not 1 <= amount <= 200:
            await interaction.response.send_message(
                "❌ Please specify a number between 1 and 200!",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        
        await interaction.followup.send(
            f"🗑️ Successfully deleted {len(deleted)} messages!",
            ephemeral=True
        )

    except discord.Forbidden:
        await interaction.followup.send(
            "❌ I don't have permission to delete messages!",
            ephemeral=True
        )
    except Exception as e:
        print(f"Error in deletemessage command: {e}")
        await interaction.followup.send("❌ An error occurred!", ephemeral=True)

@bot.tree.command(name="deleteusermessage", description="Delete messages from a specific user")
@app_commands.describe(
    amount="Number of messages to delete (1-200)",
    target="The user whose messages to delete"
)
@commands.cooldown(1, 5, commands.BucketType.channel)
async def deleteusermessage(
    interaction: discord.Interaction, 
    amount: int,
    target: discord.Member
):
    """Delete messages from a specific user"""
    try:
        if not await has_mod_role(interaction):
            await interaction.response.send_message(
                "🔒 You need moderator role to use this command!",
                ephemeral=True
            )
            return

        if target.bot:
            await interaction.response.send_message(
                "🤖 That's a bot! Use `/deletebotmessage` for bot messages!",
                ephemeral=True
            )
            return

        if not 1 <= amount <= 200:
            await interaction.response.send_message(
                "❌ Please specify a number between 1 and 200!",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        
        def message_filter(message):
            return message.author == target and not message.author.bot

        deleted = await interaction.channel.purge(
            limit=amount,
            check=message_filter
        )
        
        await interaction.followup.send(
            f"🗑️ Successfully deleted {len(deleted)} messages from {target.mention}!",
            ephemeral=True
        )

    except discord.Forbidden:
        await interaction.followup.send(
            "❌ I don't have permission to delete messages!",
            ephemeral=True
        )
    except Exception as e:
        print(f"Error in deleteusermessage command: {e}")
        await interaction.followup.send("❌ An error occurred!", ephemeral=True)

@bot.tree.command(name="deletebotmessage", description="Delete messages from a specific bot")
@app_commands.describe(
    amount="Number of messages to delete (1-200)",
    target="The bot whose messages to delete"
)
@commands.cooldown(1, 5, commands.BucketType.channel)
async def deletebotmessage(
    interaction: discord.Interaction, 
    amount: int,
    target: discord.Member
):
    """Delete messages from a specific bot"""
    try:
        if not await has_mod_role(interaction):
            await interaction.response.send_message(
                "🔒 You need moderator role to use this command!",
                ephemeral=True
            )
            return

        if not target.bot:
            await interaction.response.send_message(
                "👤 That's a user! Use `/deleteusermessage` for user messages!",
                ephemeral=True
            )
            return

        if not 1 <= amount <= 200:
            await interaction.response.send_message(
                "❌ Please specify a number between 1 and 200!",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        
        def message_filter(message):
            return message.author == target and message.author.bot

        deleted = await interaction.channel.purge(
            limit=amount,
            check=message_filter
        )
        
        await interaction.followup.send(
            f"🗑️ Successfully deleted {len(deleted)} messages from bot {target.mention}!",
            ephemeral=True
        )

    except discord.Forbidden:
        await interaction.followup.send(
            "❌ I don't have permission to delete messages!",
            ephemeral=True
        )
    except Exception as e:
        print(f"Error in deletebotmessage command: {e}")
        await interaction.followup.send("❌ An error occurred!", ephemeral=True)

# Add new command for setting mod role
@bot.tree.command(name="modrole", description="Set the moderator role for command access")
@app_commands.describe(role="The role to set as moderator")
@app_commands.default_permissions(administrator=True)
async def setmodrole(interaction: discord.Interaction, role: discord.Role):
    """Set the moderator role for command access"""
    try:
        bot.mod_roles[interaction.guild.id] = role.id
        await interaction.response.send_message(
            f"✅ Successfully set {role.mention} as the moderator role!",
            ephemeral=True
        )
    except Exception as e:
        print(f"Error in setmodrole command: {e}")
        await interaction.response.send_message("❌ An error occurred!", ephemeral=True)

# Helper function to check mod role
async def has_mod_role(interaction: discord.Interaction) -> bool:
    """Check if user has mod role or required permissions"""
    if interaction.user.guild_permissions.administrator:
        return True
    
    mod_role_id = bot.mod_roles.get(interaction.guild.id)
    if mod_role_id and mod_role_id in [role.id for role in interaction.user.roles]:
        return True
    
    return False

if __name__ == "__main__":
    try:
        keep_alive()  # Start the web server
        print("✅ Web server started!")
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")