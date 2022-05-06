import datetime
import json
import logging
import os
import sqlite3
from sqlite3 import Error

import nextcord
import pyrogram
import requests
from nextcord.ext import commands
from nextcord.ui import *

configFile = json.load(open("config.json"))
messageFile = json.load(open("messagetable.json"))
logging.basicConfig(
    format=configFile["logging"]["loggingFormat"],
    level=logging.INFO
    if configFile["logging"]["loggingLevel"].lower() == "info"
    else logging.DEBUG,
)

tgInstance = pyrogram.Client(
    "Discogram",
    api_id=configFile["telegram"]["api_id"],
    api_hash=configFile["telegram"]["api_hash"],
)
discordClient = commands.Bot(command_prefix="$")

class sendMessage(nextcord.ui.Modal):
    def __init__(self):
        self.stringsDict = messageFile["modals"]["sendMessage"]
        super().__init__(self.stringsDict["modalTitle"])
        self.username = nextcord.ui.TextInput(
            label=self.stringsDict["UsernameLabel"],
            placeholder=self.stringsDict["UsernamePlaceholder"],
            required=True,
            max_length=32,
        )
        self.add_item(self.username)

        self.text = nextcord.ui.TextInput(
            label=self.stringsDict["TextLabel"],
            placeholder=self.stringsDict["TextPlaceholder"],
            style=nextcord.TextInputStyle.paragraph,
            min_length=2,
            max_length=500,
            required=True
        )
        self.add_item(self.text)

    async def callback(self, interaction: nextcord.Interaction) -> None:
        try:
            id = await tgInstance.resolve_peer(self.username.value)
            await tgInstance.send_message(
                "-100" + str(id.channel_id)
                if type(id) == pyrogram.raw.types.InputPeerChannel
                else id.user_id,
                self.text.value,
            )
        except Exception as e:
            await interaction.send(
                messageFile["errorMessage"] + str(e), ephemeral=True
            )
        try:
            id.user_id
            await on_forced_ticket(
                id.user_id,
                interaction.user.name,
                self.username.value,
                self.text.value,
                True
            )
            await interaction.send(self.stringsDict["MessageSentResponse"], ephemeral=True)
        except Exception as e:
            await interaction.send(
                messageFile["errorMessage"] + str(e), ephemeral=True
            )


class cronologiaModal(nextcord.ui.Modal):
    def __init__(self):
        self.stringsDict = messageFile["modals"]["cronologia"]
        super().__init__(self.stringsDict["modalTitle"])
        self.username = nextcord.ui.TextInput(
            label=self.stringsDict["UsernameLabel"],
            placeholder=self.stringsDict["UsernamePlaceholder"],
            required=True,
            max_length=32,
        )
        self.add_item(self.username)

    async def callback(self, interaction: nextcord.Interaction) -> None:
        try:
            messages = []
            i = 0
            async for message in tgInstance.get_chat_history(
                self.username.value, limit=10
            ):
                messages.append(
                    eval(f"""f'''{self.stringsDict['MessageTemplate']}'''""")
                )
                i += 1
            messages.reverse()
            await interaction.send(self.stringsDict["MessagesPrefix"] + "".join(messages))
        except Exception as e:
            await interaction.send(
                messageFile["errorMessage"] + str(e), ephemeral=True
            )


def conndb():
    db_conn = sqlite3.connect(r"./messages.db")
    cur = db_conn.cursor()
    return db_conn, cur


def fetchone(cur, what, where, whereval, orderstr):
    cur.execute(
        f"""SELECT {what} FROM tickets WHERE {where} = '{whereval}' {orderstr}"""
    )
    res = cur.fetchone()
    try:
        return res[0]
    except:
        return None


def insert(cur, values):
    cur.execute(f"""INSERT INTO tickets VALUES {values}""")


async def on_forced_ticket(id, name, username, content, is_dm):
    db_conn, cur = conndb()
    res = fetchone(cur, "is_closed", "user_id", str(id), "ORDER BY date DESC")
    channel = discordClient.get_channel(configFile["discord"]["channel_id"])
    if res is None or res == "True":
        cur.execute("select id from tickets order by date desc")
        res = cur.fetchone()
        message_res = await channel.send(
            eval(f"f'{messageFile['forcedTicketTemplate']}'")
        )
        to_add = (
            0
            if res == None
            else int(res[0].replace(configFile["discord"]["IDPrefix"], ""))
        )
        ticket_id = configFile["discord"]["IDPrefix"] + str(1 + to_add)
        await message_res.create_thread(name=f"{ticket_id}")
        insert(
            cur,
            f"""('{ticket_id}',
                {message_res.id},
                {int(datetime.datetime.now().timestamp())},
                {id},
                '{content}',
                'false',
                '{'true' if is_dm else 'false'}')""",
        )

        db_conn.commit()
    else:
        mess_id = fetchone(cur, "message_id", "user_id", str(id), "ORDER BY date DESC")
        try:
            await channel.get_thread(mess_id).send(content)
        except nextcord.errors.HTTPException:
            pass
    cur.close()
    db_conn.close()


async def on_tg_message(client, message, is_dm):
    db_conn, cur = conndb()
    res = fetchone(
        cur, "is_closed", "user_id", str(message.from_user.id), "ORDER BY date DESC"
    )
    channel = discordClient.get_channel(configFile["discord"]["channel_id"])
    if (
        message.from_user.id in messageFile["ignoreTGAuthor"]
    ):
        pass
    elif res is None or res == "True":
        first_name, last_name, full_name = await welcomeAndInitNames(message)
        cur.execute("select id from tickets order by date desc")
        res = cur.fetchone()
        message_res = await channel.send(
            eval(f"f'{messageFile['startingMessageTemplate']}'")
        )
        to_add = (
            0
            if res == None
            else int(res[0].replace(configFile["discord"]["IDPrefix"], ""))
        )
        ticket_id = configFile["discord"]["IDPrefix"] + str(1 + to_add)
        await message_res.create_thread(name=f"{ticket_id}")
        insert(
            cur,
            f"""('{ticket_id}',
                {message_res.id},
                {int(datetime.datetime.now().timestamp())},
                {message.from_user.id},
                '{message.text}',
                'false',
                '{'true' if is_dm else 'false'}')""",
        )

        db_conn.commit()
    else:
        mess_id = fetchone(
            cur,
            "message_id",
            "user_id",
            str(message.from_user.id),
            "ORDER BY date DESC",
        )
        try:
            await channel.get_thread(mess_id).send(message.text)
        except nextcord.errors.HTTPException:
            pass
    cur.close()
    db_conn.close()


async def welcomeAndInitNames(message):
    await message.reply(messageFile["welcome"])
    first_name = (
        message.from_user.first_name if message.from_user.first_name is not None else ""
    )
    last_name = (
        message.from_user.last_name if message.from_user.last_name is not None else ""
    )
    full_name = f"{first_name} {last_name}".replace("  ", " ")
    return first_name, last_name, full_name


async def on_tg_message_media(client, message, is_dm):
    db_conn, cur = conndb()
    res = fetchone(
        cur, "is_closed", "user_id", str(message.from_user.id), "ORDER BY date DESC"
    )
    channel = discordClient.get_channel(configFile["discord"]["channel_id"])
    if res is None or res == "True":
        first_name, last_name, full_name = await welcomeAndInitNames(message)
        path = await tgInstance.download_media(message=message, in_memory=True)

        message_res = await channel.send(
            eval(f"f'{messageFile['startingMessageTemplateMedia']}'"),
            file=nextcord.File(path),
        )
        cur.execute("select id from tickets order by date desc")
        res = cur.fetchone()
        to_add = (
            0
            if res == None
            else int(res[0].replace(configFile["discord"]["IDPrefix"], ""))
        )
        ticket_id = configFile["discord"]["IDPrefix"] + str(1 + to_add)
        await message_res.create_thread(name=f"{ticket_id}")
        insert(
            cur,
            f"""('{ticket_id}',
                {message_res.id},
                {int(datetime.datetime.now().timestamp())},
                {message.from_user.id},
                '{message.text}',
                'false',
                '{'true' if is_dm else 'false'}')""",
        )

        db_conn.commit()
    else:
        mess_id = fetchone(
            cur,
            "message_id",
            "user_id",
            str(message.from_user.id),
            "ORDER BY date DESC",
        )
        path = await tgInstance.download_media(message=message, in_memory=True)
        await channel.get_thread(mess_id).send(
            message.caption, file=nextcord.File(path)
        )
    cur.close()
    db_conn.close()


async def close_ticket(message, motivazione):
    guild = discordClient.get_channel(configFile["discord"]["channel_id"])
    db_conn, cur = conndb()
    
    mess_id = fetchone(cur, "message_id", "id", message.channel.name, "")
    thread = guild.get_thread(mess_id)
    user_id = fetchone(cur, "user_id", "id", message.channel.name, "")
    cur.execute(
        f"""
        UPDATE tickets
        SET is_closed = "True"
        WHERE id = '{message.channel.name}'
        """
    )
    db_conn.commit()
    await message.reply("Ticket chiuso.")
    motivoSuffix = (
        f"\n\nMotivazione: {' '.join(motivazione) if motivazione != '' else ''}"
    )
    await tgInstance.send_message(
        user_id, messageFile["closedTicketTG"] + motivoSuffix
    )
    await thread.edit(
        name=thread.name + messageFile["closedThread"], archived=True, locked=True
    )
    cur.close()
    db_conn.close()


@discordClient.event
async def on_message(message):
    if (
        message.content.startswith("/closeticket")
        or message.content.startswith("/close")
        and message.author.id != discordClient.application_id
    ):
        try:
            motivo = message.content.split(" ")[1:]
        except:
            motivo = ""
        await close_ticket(message, motivo)
    elif type(message.channel) == nextcord.channel.TextChannel:
        pass
    elif (
        message.attachments != []
        and type(message.channel) == nextcord.threads.Thread
        and not message.content.startswith(configFile["discord"]["ignoreMessagePrefix"])
        and message.author.id != discordClient.application_id
    ):
        db_conn, cur = conndb()
        ticket = fetchone(cur, "user_id", "id", message.channel.name, "")

        for attachment in message.attachments:
            open(os.path.join("./downloads", attachment.filename), "wb").write(
                requests.get(attachment.url).content
            )
            if message.attachments[-1].url == attachment.url:
                await tgInstance.send_document(
                    chat_id=ticket,
                    document=os.path.join("./downloads", attachment.filename),
                    caption=message.content,
                )
            else:
                await tgInstance.send_document(
                    chat_id=ticket,
                    document=os.path.join("./downloads", attachment.filename),
                    caption=message.content
                )
            os.remove(os.path.join("./downloads", attachment.filename))
        cur.close()
        db_conn.close()
    elif (
        type(message.channel) == nextcord.threads.Thread
        and not message.content.startswith(configFile["discord"]["ignoreMessagePrefix"])
        and message.author.id != discordClient.application_id
    ):
        db_conn, cur = conndb()
        ticket = fetchone(cur, "user_id", "id", message.channel.name, "")
        try:
            await tgInstance.send_message(chat_id=ticket, text=message.content)
        except:
            pass
        cur.close()
        db_conn.close()


@tgInstance.on_message(pyrogram.filters.private)
async def on_private_message(client, message):
    if message.media:
        await on_tg_message_media(client, message, True)
    await on_tg_message(client, message, True)


def create_connection(db_file):
    db_conn = sqlite3.connect(db_file)
    cur = db_conn.cursor()
    pass
    try:
        cur.execute(
            "CREATE TABLE tickets (id integer, message_id integer, date integer, user_id integer, text_ticket text, is_closed text, is_dm text)"
        )
        db_conn.commit()
    except Error:
        pass
    cur.close()
    db_conn.close()


@discordClient.slash_command(name="send", description="Manda un messaggio")
async def send(interaction: nextcord.Interaction):
    modal = sendMessage()
    try:
        await interaction.response.send_modal(modal)
    except Exception as e:
        pass


@discordClient.slash_command(
    name="cronologia", description="Guarda i primi 10 messaggi di una persona!"
)
async def cronologia(interaction: nextcord.Integration):
    modal = cronologiaModal()
    try:
        await interaction.response.send_modal(modal)
    except Exception as e:
        pass


if __name__ == "__main__":
    create_connection(r"./messages.db")
    try:
        os.mkdir("./downloads")
    except FileExistsError:
        pass
    tgInstance.start()
    discordClient.run(configFile["discord"]["token"])
    os.rmdir("./downloads")
