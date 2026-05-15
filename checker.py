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

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is ready to check FFlags!')

@bot.command(name='checkfflags', aliases=['checkflags', 'fflagcheck'])
async def check_fflags(ctx):
    if not ctx.message.attachments:
        await ctx.send("❌ Please upload a JSON or TXT file with the command.\nUsage: `!checkfflags` and attach a file")
        return
    
    attachment = ctx.message.attachments[0]
    
    start_time = time.time()
    
    status_msg = await ctx.send("🔄 Checking FFlags...")
    
    try:
        website_fflags = await FFlagChecker.fetch_fflags()
        
        file_content = await attachment.read()
        file_text = file_content.decode('utf-8')
        
        local_fflags = FFlagChecker.parse_uploaded_file(file_text, attachment.filename)
        
        valid_fflags, invalid_fflags = FFlagChecker.compare_fflags(local_fflags, website_fflags)
        
        total_time = time.time() - start_time
        
        await status_msg.delete()
        
        response = f"## 📊 FFlag Results\n\n"
        response += f"**File:** `{attachment.filename}`\n"
        response += f"**Total flags checked:** {len(local_fflags)}\n"
        response += f"**✅ Valid flags:** {len(valid_fflags)}\n"
        response += f"**❌ Invalid flags:** {len(invalid_fflags)}\n"
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
    else:
        print("Starting Discord bot...")
        asyncio.run(main())
