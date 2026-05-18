import discord
from discord.ext import commands
import aiohttp
import json
import os
from typing import Dict, List, Set, Tuple
from datetime import datetime
import io
import asyncio
import time
import re

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
PREFIX = '!'

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

FFLAGS_URL = "https://imtheo.lol/Offsets/FFlags.json"

# Try to import Flask, but don't fail if it's not available
try:
    from flask import Flask
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("Flask not available, web server will not start")

if FLASK_AVAILABLE:
    app = Flask(__name__)

    @app.route('/')
    def home():
        return "Discord FFlag Bot is running!"

    def run_web_server():
        port = int(os.environ.get('PORT', 8080))
        app.run(host='0.0.0.0', port=port)

class FFlagChecker:
    @staticmethod
    async def fetch_fflags() -> Dict:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(FFLAGS_URL, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        fflags = data.get("FFlagOffsets", {}).get("FFlags", {})
                        return fflags
                    else:
                        raise Exception(f"Failed to fetch FFlags. Status code: {response.status}")
            except Exception as e:
                raise Exception(f"Error fetching FFlags: {str(e)}")

    @staticmethod
    def parse_json_content(content: str) -> Dict:
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return data
            elif isinstance(data, list):
                return {flag: "" for flag in data}
            else:
                raise Exception("JSON format not recognized")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON: {str(e)}")

    @staticmethod
    def parse_uploaded_file(content: str, filename: str) -> Dict:
        try:
            if filename.lower().endswith('.json'):
                data = json.loads(content)
                if isinstance(data, dict):
                    return data
                elif isinstance(data, list):
                    return {flag: "" for flag in data}
                else:
                    raise Exception("JSON format not recognized")
            else:
                try:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        return data
                    elif isinstance(data, list):
                        return {flag: "" for flag in data}
                except json.JSONDecodeError:
                    pass
                
                result = {}
                for line in content.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            parts = line.split('=', 1)
                            flag = parts[0].strip()
                            value = parts[1].strip() if len(parts) > 1 else ""
                            result[flag] = value
                        elif ':' in line:
                            try:
                                parts = line.split(':', 1)
                                flag = parts[0].strip().strip('"\'')
                                value = parts[1].strip().strip('"\',')
                                result[flag] = value
                            except:
                                result[line] = ""
                        else:
                            result[line] = ""
                return result
        except Exception as e:
            raise Exception(f"Error parsing file: {str(e)}")

    @staticmethod
    def compare_fflags(local_fflags: Dict, website_fflags: Dict[str, int]) -> Tuple[Dict, Dict]:
        valid_fflags = {}
        invalid_fflags = {}
        
        website_flag_names = set(website_fflags.keys())
        prefixes = ['FFlag', 'DFInt', 'FInt', 'DFFlag', 'DFLog', 'FLog', 'DFString', 'FString']
        
        for flag, value in local_fflags.items():
            matched = False
            
            if flag in website_flag_names:
                valid_fflags[flag] = value
                matched = True
            else:
                for prefix in prefixes:
                    if flag.startswith(prefix):
                        flag_clean = flag[len(prefix):]
                        if flag_clean in website_flag_names:
                            valid_fflags[flag] = value
                            matched = True
                            break
                
                if not matched:
                    for prefix in prefixes:
                        flag_with_prefix = prefix + flag
                        if flag_with_prefix in website_flag_names:
                            valid_fflags[flag] = value
                            matched = True
                            break
            
            if not matched:
                invalid_fflags[flag] = value
        
        return valid_fflags, invalid_fflags

    @staticmethod
    def combine_fflags(all_fflags: List[Dict]) -> Dict:
        combined = {}
        
        for fflag_dict in all_fflags:
            for key, value in fflag_dict.items():
                if key not in combined:
                    combined[key] = value
        
        return combined

    @staticmethod
    def create_json_file(data: Dict, flag_type: str) -> io.BytesIO:
        file_data = io.BytesIO()
        json_content = json.dumps(data, indent=4, ensure_ascii=False)
        file_data.write(json_content.encode('utf-8'))
        file_data.seek(0)
        return file_data

    @staticmethod
    def format_time(seconds: float) -> str:
        if seconds < 0.001:
            return f"{seconds * 1000000:.0f}µs"
        elif seconds < 1:
            return f"{seconds * 1000:.2f}ms"
        else:
            return f"{seconds:.2f}s"

class PaginatorView(discord.ui.View):
    def __init__(self, pages: List[str], total_fflags: int, current_page: int = 0):
        super().__init__(timeout=None)
        self.pages = pages
        self.total_fflags = total_fflags
        self.current_page = current_page
        self.total_pages = len(pages)
    
    async def update_message(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 All FFlags",
            description=self.pages[self.current_page],
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages} | Total FFlags: {self.total_fflags}")
        
        # Update button states
        self.previous_page_button.disabled = self.current_page == 0
        self.next_page_button.disabled = self.current_page == self.total_pages - 1
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary, custom_id="fflag_prev")
    async def previous_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)
    
    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary, custom_id="fflag_next")
    async def next_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            await self.update_message(interaction)
    
    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger, custom_id="fflag_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()

class InjectorSelectView(discord.ui.View):
    def __init__(self, injectors: List[Dict]):
        super().__init__(timeout=None)
        self.injectors = injectors
        
        # Create a select menu
        select = discord.ui.Select(
            placeholder="Select an FFlag Injector...",
            options=[
                discord.SelectOption(
                    label=injector['name'],
                    description=f"Version: {injector['current_version']}",
                    value=str(i),
                    emoji="💉"
                ) for i, injector in enumerate(injectors)
            ],
            custom_id="injector_select"
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        selected_index = int(interaction.data["values"][0])
        injector = self.injectors[selected_index]
        
        # Create embed for selected injector
        embed = discord.Embed(
            title=f"💉 {injector['name']}",
            color=discord.Color.purple()
        )
        
        # Add fields
        embed.add_field(name="Discord", value=f"[Click to Join]({injector['discord']})", inline=False)
        embed.add_field(name="Products", value="\n".join([f"• {product}" for product in injector['products']]), inline=False)
        
        # Updated status with emoji
        updated_status = "✅ Yes" if injector['updated_and_working'] else "❌ No"
        embed.add_field(name="Updated And Working", value=updated_status, inline=True)
        embed.add_field(name="Current Version", value=injector['current_version'], inline=True)
        
        # Add download links
        download_links = ""
        for name, url in injector['downloads'].items():
            if url:
                download_links += f"• **{name}:** [Download]({url})\n"
            else:
                download_links += f"• **{name}:** Not Available\n"
        
        embed.add_field(name="Downloads", value=download_links, inline=False)
        
        # Add footer
        embed.set_footer(text=f"Select an injector from the dropdown menu above")
        
        await interaction.response.edit_message(embed=embed, view=self)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is ready to check FFlags!')

@bot.command(name='checkfflags', aliases=['checkflags', 'fflagcheck'])
async def check_fflags(ctx, *, json_content: str = None):
    start_time = time.time()
    
    # Method 1: Check if there's an attachment
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        
        if not attachment.filename.endswith(('.json', '.txt')):
            await ctx.send("❌ Please upload a JSON or TXT file")
            return
        
        status_msg = await ctx.send("🔄 Checking FFlags...")
        
        try:
            website_fflags = await FFlagChecker.fetch_fflags()
            
            file_content = await attachment.read()
            file_text = file_content.decode('utf-8')
            
            local_fflags = FFlagChecker.parse_uploaded_file(file_text, attachment.filename)
            
            valid_fflags, invalid_fflags = FFlagChecker.compare_fflags(local_fflags, website_fflags)
            
            total_time = time.time() - start_time
            
            await status_msg.delete()
            
            # Determine method based on file extension
            if attachment.filename.lower().endswith('.json'):
                method = "JSON File"
            else:
                method = "TXT File"
            
            response = f"## 📊 FFlag Results\n\n"
            response += f"**Method:** {method}\n"
            response += f"**Total FFlags:** {len(local_fflags)}\n"
            response += f"**✅ Valid FFlags:** {len(valid_fflags)}\n"
            response += f"**❌ Invalid FFlags:** {len(invalid_fflags)}\n"
            response += f"**⏱️ Time taken:** {FFlagChecker.format_time(total_time)}\n"
            
            await ctx.send(response)
            
            if valid_fflags:
                valid_file = FFlagChecker.create_json_file(valid_fflags, "valid")
                await ctx.send(file=discord.File(valid_file, filename=f"valid_fflags.json"))
            
            if invalid_fflags:
                invalid_file = FFlagChecker.create_json_file(invalid_fflags, "invalid")
                await ctx.send(file=discord.File(invalid_file, filename=f"invalid_fflags.json"))
            
            if not valid_fflags and not invalid_fflags:
                await ctx.send("❌ No flags were found in the uploaded file")
            
        except Exception as e:
            await status_msg.edit(content=f"❌ Error: {str(e)}")
    
    # Method 2: Check if there's JSON in the message
    elif json_content:
        status_msg = await ctx.send("🔄 Checking FFlags...")
        
        try:
            website_fflags = await FFlagChecker.fetch_fflags()
            
            local_fflags = FFlagChecker.parse_json_content(json_content)
            
            valid_fflags, invalid_fflags = FFlagChecker.compare_fflags(local_fflags, website_fflags)
            
            total_time = time.time() - start_time
            
            await status_msg.delete()
            
            response = f"## 📊 FFlag Results\n\n"
            response += f"**Method:** In Message\n"
            response += f"**Total FFlags:** {len(local_fflags)}\n"
            response += f"**✅ Valid FFlags:** {len(valid_fflags)}\n"
            response += f"**❌ Invalid FFlags:** {len(invalid_fflags)}\n"
            response += f"**⏱️ Time taken:** {FFlagChecker.format_time(total_time)}\n"
            
            await ctx.send(response)
            
            if valid_fflags:
                valid_file = FFlagChecker.create_json_file(valid_fflags, "valid")
                await ctx.send(file=discord.File(valid_file, filename=f"valid_fflags.json"))
            
            if invalid_fflags:
                invalid_file = FFlagChecker.create_json_file(invalid_fflags, "invalid")
                await ctx.send(file=discord.File(invalid_file, filename=f"invalid_fflags.json"))
            
            if not valid_fflags and not invalid_fflags:
                await ctx.send("❌ No flags were found in the message")
            
        except Exception as e:
            await status_msg.edit(content=f"❌ Error: {str(e)}")
    
    else:
        await ctx.send("❌ Please either:\n1. Upload a JSON or TXT file with the command\n2. Or provide JSON in the message\n\n**Usage:**\n`!checkfflags` (with attached file)\n`!checkfflags {\"FFlagExample\": \"True\"}`")

@bot.command(name='combinefflags', aliases=['combineflags', 'fflagcombine'])
async def combine_fflags(ctx):
    if not ctx.message.attachments:
        await ctx.send("❌ Please upload JSON or TXT files with the command.\nUsage: `!combinefflags` and attach multiple files")
        return
    
    status_msg = await ctx.send("🔄 Combining FFlags...")
    start_time = time.time()
    
    try:
        all_fflags = []
        files_processed = 0
        
        for attachment in ctx.message.attachments:
            if not attachment.filename.endswith(('.json', '.txt')):
                await ctx.send(f"⚠️ Skipping `{attachment.filename}` - not a JSON or TXT file")
                continue
            
            file_content = await attachment.read()
            file_text = file_content.decode('utf-8')
            
            fflags_dict = FFlagChecker.parse_uploaded_file(file_text, attachment.filename)
            all_fflags.append(fflags_dict)
            files_processed += 1
        
        if not all_fflags:
            await status_msg.edit(content="❌ No valid JSON or TXT files found to combine")
            return
        
        combined_fflags = FFlagChecker.combine_fflags(all_fflags)
        
        total_time = time.time() - start_time
        
        await status_msg.delete()
        
        response = f"## 📊 FFlag Results\n\n"
        response += f"**Files:** {files_processed}\n"
        response += f"**Total FFlags:** {len(combined_fflags)}\n"
        response += f"**⏱️ Time taken:** {FFlagChecker.format_time(total_time)}\n"
        
        await ctx.send(response)
        
        combined_file = FFlagChecker.create_json_file(combined_fflags, "combined")
        await ctx.send(file=discord.File(combined_file, filename=f"combined_fflags.json"))
        
    except Exception as e:
        await status_msg.edit(content=f"❌ Error: {str(e)}")

@bot.command(name='listfflags', aliases=['listflags', 'fflagslist'])
async def list_fflags(ctx):
    status_msg = await ctx.send("🔄 Fetching FFlags list...")
    
    try:
        website_fflags = await FFlagChecker.fetch_fflags()
        
        if not website_fflags:
            await status_msg.edit(content="❌ No FFlags found or failed to fetch")
            return
        
        # Sort FFlags alphabetically
        sorted_fflags = sorted(website_fflags.keys())
        total_fflags = len(sorted_fflags)
        
        # Create pages with 30 FFlags per page
        fflags_per_page = 30
        pages = []
        
        for i in range(0, total_fflags, fflags_per_page):
            page_fflags = sorted_fflags[i:i + fflags_per_page]
            page_content = "```\n"
            for idx, flag in enumerate(page_fflags, start=i + 1):
                page_content += f"{idx:4}. {flag}\n"
            page_content += "```"
            pages.append(page_content)
        
        await status_msg.delete()
        
        # Create initial embed
        embed = discord.Embed(
            title="📋 All FFlags",
            description=pages[0],
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Page 1/{len(pages)} | Total FFlags: {total_fflags}")
        
        # Create paginator view with no timeout
        view = PaginatorView(pages, total_fflags, 0)
        
        # Update button states for first page
        view.previous_page_button.disabled = True
        view.next_page_button.disabled = len(pages) == 1
        
        await ctx.send(embed=embed, view=view)
        
    except Exception as e:
        await status_msg.edit(content=f"❌ Error: {str(e)}")

@bot.command(name='fflaginjectors', aliases=['injectors', 'fflaginjector'])
async def fflag_injectors(ctx):
    # Define injectors data
    injectors = [
        {
            "name": "Velostrap",
            "discord": "https://discord.com/invite/4Gb4FYUQCm",
            "products": ["FFlag Injector (exe)", "FFlag Injector (AHK)", "Bootstrapper (exe)"],
            "updated_and_working": False,
            "current_version": "1.0.0.0",
            "downloads": {
                "FFlag Injector (exe)": "https://cdn.discordapp.com/attachments/1496510448076329130/1502244748356751441/Velostrap.exe?ex=6a0b8832&is=6a0a36b2&hm=27104b8de0f4cd2e1d175790b8178c1888691691d677fc572f819a6e5866bf9e&",
                "FFlag Injector (AHK)": "https://cdn.discordapp.com/attachments/1497578849053970514/1502569731196981289/VeloAHK.ahk?ex=6a0b655c&is=6a0a13dc&hm=4e7eb8b17cb11179bd72039c3fc6d9b1bb475c532c97052e19275bb9bf99125f&",
                "Bootstrapper (exe)": "https://download2330.mediafire.com/xi6huu9xmsagNcBwGssKYUkFTG5M6XhVXoBjT6C5ZSbnVgt8UQwR24MPW5zq2eqquMi1EACNSaYp1kqzvZFmP48LEz2xSKeTAlKcxIlTC3PgV-TYnrTSKmiONh_u_xScjb_5-SU5Z32x5HF0oEVqsqbr6Tb1qO-FD4XPi7fQoMCTfA/u4m3hafb7jj0cq5/Velostrap.exe"
            }
        },
        {
            "name": "Leitostrap",
            "discord": "https://discord.gg/cQGsgkatyh",
            "products": ["FFlag Injector (exe)", "FFlag Injector (AHK)"],
            "updated_and_working": True,
            "current_version": "V4.0.0",
            "downloads": {
                "FFlag Injector (exe)": "https://github.com/Leitostrap/Leitostrap/releases/download/Leitostrap_V4.0.0/Leitostrap.exe",
                "FFlag Injector (AHK)": "https://cdn.discordapp.com/attachments/1505268462313013341/1505273810939809862/Leitostrap.ahk?ex=6a0b587b&is=6a0a06fb&hm=690322f269671f40cdf16ec8a453743981cbb1ba4e1204158b6567c9731b6e7e&",
                "Bootstrapper (exe)": None
            }
        }
    ]
    
    # Create initial embed with dropdown menu
    embed = discord.Embed(
        title="💉 FFlag Injectors",
        description="Select an injector from the dropdown menu below to view details and download links.",
        color=discord.Color.purple()
    )
    embed.add_field(name="Total Injectors", value=str(len(injectors)), inline=True)
    embed.add_field(name="How to Use", value="1. Select an injector from the dropdown\n2. View all information and download links\n3. Click the download links to get the files", inline=False)
    embed.set_footer(text="FFlag Injector Database")
    
    view = InjectorSelectView(injectors)
    
    await ctx.send(embed=embed, view=view)

async def main():
    if FLASK_AVAILABLE:
        import threading
        thread = threading.Thread(target=run_web_server)
        thread.daemon = True
        thread.start()
        print("Web server started on port", os.environ.get('PORT', 8080))
    
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN environment variable not set!")
        print("Please set the DISCORD_BOT_TOKEN environment variable in Render dashboard")
    else:
        print("Starting Discord bot...")
        asyncio.run(main())
