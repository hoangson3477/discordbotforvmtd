import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import logging

from config import SupabaseConfig, logger

# Initialize client
supabase = SupabaseConfig.validate_main()

# =========================
# MODAL TRẢ LỜI FORM
# =========================
class FormModal(discord.ui.Modal):
    def __init__(self, form, guild_id, staff_channel_id, start=0, answers=None):
        super().__init__(title=form["title"][:45])

        self.form = form
        self.guild_id = guild_id
        self.staff_channel_id = staff_channel_id
        self.start = start
        self.answers = answers or []
        self.inputs = []

        questions = form["questions"][start:start+5]

        for q in questions:
            inp = discord.ui.TextInput(
                label=q["label"][:45],
                required=True,
                max_length=1000
            )
            self.add_item(inp)
            self.inputs.append(inp)

    async def on_submit(self, interaction: discord.Interaction):
        for i in self.inputs:
            self.answers.append(i.value)

        next_start = self.start + 5

        # Nếu còn câu hỏi → mở modal tiếp
        if next_start < len(self.form["questions"]):
            next_modal = FormModal(
                self.form,
                self.guild_id,
                self.staff_channel_id,
                start=next_start,
                answers=self.answers
            )
            return await interaction.response.send_modal(next_modal)

        # Nếu hết → lưu DB
        supabase.table("unit_form_responses").insert({
            "form_id": self.form["id"],
            "guild_id": self.guild_id,
            "user_id": str(interaction.user.id),
            "answers": self.answers
        }).execute()

        # Gửi log
        if self.staff_channel_id:
            ch = interaction.guild.get_channel(int(self.staff_channel_id))
            if ch:
                embed = discord.Embed(
                    title=f"📥 Đơn mới - Form {self.form['id']}",
                    color=discord.Color.green()
                )
                embed.add_field(name="User", value=interaction.user.mention, inline=False)

                for i, ans in enumerate(self.answers):
                    embed.add_field(
                        name=f"Câu {i+1}",
                        value=ans[:1024],
                        inline=False
                    )

                await ch.send(embed=embed)

        await interaction.response.send_message(
            "✅ Đã nộp đơn thành công!",
            ephemeral=True
        )

# =========================
# BUTTON VIEW
# =========================
class FormView(discord.ui.View):
    def __init__(self, bot, form):
        super().__init__(timeout=None)
        self.bot = bot
        self.form = form

    @discord.ui.button(label="📩 Nộp đơn", style=discord.ButtonStyle.green)
    async def start_form(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message(
            "📩 Hãy check DM của bạn để bắt đầu làm form.",
            ephemeral=True
        )

        user = interaction.user

        try:
            dm = await user.create_dm()
        except:
            return

        await dm.send(
            f"**{self.form['title']}**\n\n"
            "Gõ `sẵn sàng` để bắt đầu làm form."
        )

        def check(m):
            return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=300)
        except:
            return await dm.send("Hết thời gian chờ. Bấm nút lại nếu muốn làm form.")

        if "sẵn" not in msg.content.lower():
            return await dm.send("Huỷ form.")

        answers = []

        # hỏi từng câu
        for idx, q in enumerate(self.form["questions"], start=1):
            await dm.send(f"**Câu {idx}:** {q['label']}")

            try:
                reply = await self.bot.wait_for("message", check=check, timeout=600)
            except:
                return await dm.send("Bạn trả lời quá lâu, form đã bị huỷ.")

            answers.append(reply.content)

        # lưu DB
        supabase.table("unit_form_responses").insert({
            "form_id": self.form["id"],
            "guild_id": self.form["guild_id"],
            "user_id": str(user.id),
            "answers": answers
        }).execute()

        await dm.send("✅ Bạn đã hoàn thành form!")

        # gửi log staff
        if self.form.get("staff_channel_id"):
            staff_channel = interaction.guild.get_channel(int(self.form["staff_channel_id"]))

            if staff_channel:
                embed = discord.Embed(
                    title=f"📥 Đơn mới - Form {self.form['id']}",
                    color=discord.Color.green()
                )

                embed.add_field(name="Người nộp", value=user.mention, inline=False)

                for i, ans in enumerate(answers):
                    question_text = self.form["questions"][i]["label"]

                    embed.add_field(
                        name=f"Câu {i+1}: {question_text[:200]}",
                        value=ans[:1024],
                        inline=False
                    )

                await staff_channel.send(embed=embed)

# =========================
# COG
# =========================
class UnitFormCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # =========================
    # CREATE FORM
    # =========================
    @commands.command(name="createform")
    async def create_form(self, ctx, staff_channel: discord.TextChannel, *, data: str):
        """
        !createform #staff-log Title | Description | Question1 ; Question2 ; Question3
        """

        try:
            title, description, questions_raw = data.split("|")
            questions = [
                {"label": q.strip(), "type": "text"}
                for q in questions_raw.split(";")
                if q.strip()
            ]

            res = supabase.table("unit_forms").insert({
                "guild_id": str(ctx.guild.id),
                "creator_id": str(ctx.author.id),
                "title": title.strip(),
                "description": description.strip(),
                "questions": questions,
                "staff_channel_id": str(staff_channel.id)
            }).execute()

            form_id = res.data[0]["id"]

            await ctx.reply(f"✅ Đã tạo form. ID: `{form_id}`")

        except Exception as e:
            await ctx.reply(f"Lỗi: {e}")

    # =========================
    # EDIT FORM
    # =========================
    @commands.command(name="editform")
    async def edit_form(self, ctx, form_id: str, *, data: str):
        """
        !editform <form_id> Title | Description | Question1 ; Question2
        """

        try:
            title, description, questions_raw = data.split("|")
            questions = [
                {"label": q.strip(), "type": "text"}
                for q in questions_raw.split(";")
                if q.strip()
            ]

            supabase.table("unit_forms") \
                .update({
                    "title": title.strip(),
                    "description": description.strip(),
                    "questions": questions
                }) \
                .eq("id", form_id) \
                .eq("guild_id", str(ctx.guild.id)) \
                .execute()

            await ctx.reply("✏️ Đã cập nhật form.")

        except Exception as e:
            await ctx.reply(f"Lỗi: {e}")

    # =========================
    # SEND FORM
    # =========================
    @commands.command(name="sendform")
    async def send_form(self, ctx, form_id: str, channel: discord.TextChannel):
        """
        !sendform <form_id> #channel
        """

        try:
            res = supabase.table("unit_forms") \
                .select("*") \
                .eq("id", form_id) \
                .eq("guild_id", str(ctx.guild.id)) \
                .single() \
                .execute()

            form = res.data
            if not form:
                return await ctx.reply("Không tìm thấy form.")

            embed = discord.Embed(
                title=form["title"],
                description=form.get("post_message") or form["description"],
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Form ID: {form_id}")

            view = FormView(self.bot, form)

            await channel.send(
                embed=embed,
                view=view
            )
            await ctx.reply("📨 Đã gửi form có nút nộp đơn.")

        except Exception as e:
            await ctx.reply(f"Lỗi: {e}")

    @commands.command(name="setformpostmessage")
    async def set_post_msg(self, ctx, form_id: int, *, text: str):
        supabase.table("unit_forms").update({
            "post_message": text
        }).eq("id", form_id).eq("guild_id", str(ctx.guild.id)).execute()

        await ctx.reply("✅ Đã cập nhật nội dung hiển thị embed.")

    @commands.command(name="listforms")
    async def list_forms(self, ctx):
        res = supabase.table("unit_forms") \
            .select("id, title") \
            .eq("guild_id", str(ctx.guild.id)) \
            .execute()

        if not res.data:
            return await ctx.reply("Chưa có form nào.")

        msg = "\n".join([f"ID: {f['id']} | {f['title']}" for f in res.data])

        await ctx.reply(f"📋 Danh sách form:\n{msg}")

async def setup(bot):
    await bot.add_cog(UnitFormCog(bot))