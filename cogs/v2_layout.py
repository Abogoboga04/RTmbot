import discord
import json

def build_v2_card(title: str = None, description: str = None, fields: list = None, color: int = None, buttons: list = None, footer: str = None, media_url: str = None, attachment_filename: str = None):
    """
    Membangun struktur JSON untuk Discord Component Type 17 (Layout V2).
    """
    card_components = []
    
    content_text = ""
    if title:
        content_text += f"# {title}\n"
    if description:
        content_text += f"{description}\n\n"
        
    if fields:
        for field in fields:
            name = field.get("name", "")
            value = field.get("value", "")
            content_text += f"**{name}**\n{value}\n\n"
            
    has_media = bool(media_url or attachment_filename is not None)
    
    if not has_media and footer:
        content_text += f"*{footer}*"
        
    if content_text.strip():
        card_components.append({
            "type": 10,
            "id": 100,
            "content": content_text.strip()
        })
    
    # Add media if provided
    if has_media:
        media_obj = {}
        if attachment_filename is not None:
            media_obj["url"] = f"attachment://{attachment_filename}"
        elif media_url:
            media_obj["url"] = media_url
            
        card_components.append({
            "type": 12,
            "id": 150,
            "items": [{
                "media": media_obj,
                "description": None,
                "spoiler": False
            }]
        })
        
        if footer:
            card_components.append({
                "type": 10,
                "id": 160,
                "content": f"*{footer}*"
            })
    
    # Add buttons
    if buttons:
        card_components.append({
            "type": 14,
            "id": 101,
            "spacing": 1,
            "divider": True
        })
        
        # Chunk buttons into groups of 5
        for row_idx in range(0, len(buttons), 5):
            button_chunk = buttons[row_idx:row_idx+5]
            button_components = []
            for i, btn in enumerate(button_chunk):
                b = {
                    "type": 2,
                    "id": 200 + row_idx + i,
                    "style": btn.get("style", 1),
                    "label": btn.get("label", "Button")
                }
                if "custom_id" in btn:
                    b["custom_id"] = btn["custom_id"]
                if "url" in btn:
                    b["url"] = btn["url"]
                if "emoji" in btn:
                    b["emoji"] = {"name": btn["emoji"]} if isinstance(btn["emoji"], str) else btn["emoji"]
                if "disabled" in btn:
                    b["disabled"] = bool(btn["disabled"])
                button_components.append(b)
                
            card_components.append({
                "type": 1,
                "id": 102 + (row_idx // 5),
                "components": button_components
            })
        
    main_card = {
        "type": 17,
        "id": 1,
        "components": card_components
    }
    if color is not None:
        main_card["accent_color"] = color
        
    return main_card

async def send_v2_message(bot, channel_id: int, components: list, files: list = None, content: str = None):
    """
    Mengirim pesan V2 menggunakan HTTP request mentah.
    """
    route = discord.http.Route('POST', '/channels/{channel_id}/messages', channel_id=channel_id)
    
    payload = {
        "components": components,
        "flags": 32768
    }
    
    if content:
        payload["content"] = content
    
    try:
        if files:
            payload["attachments"] = [f.to_dict(i) if hasattr(f, 'to_dict') else {"id": i, "filename": f.filename} for i, f in enumerate(files)]
            for file in files:
                if hasattr(file, 'fp') and hasattr(file.fp, 'seek'):
                    try:
                        file.fp.seek(0)
                    except Exception:
                        pass
            multipart = [{'name': 'payload_json', 'value': discord.utils._to_json(payload)}]
            for i, file in enumerate(files):
                multipart.append({
                    'name': f'files[{i}]',
                    'value': file.fp,
                    'filename': file.filename,
                    'content_type': 'application/octet-stream'
                })
            params = discord.http.MultipartParameters(payload=None, multipart=multipart, files=files)
            return await bot.http.send_message(channel_id, params=params)
        else:
            return await bot.http.request(route, json=payload)
    except Exception as e:
        print(f"Failed to send V2 layout: {e}")
        return {"error_msg": str(e)}

async def send_v2_webhook(bot, webhook, components: list, content: str = "", username: str = None, avatar_url: str = None):
    """
    Mengirim pesan V2 melalui webhook.
    """
    payload = {
        "content": content,
        "components": components,
        "flags": 32768
    }
    if username:
        payload["username"] = username
    if avatar_url:
        payload["avatar_url"] = avatar_url
        
    route = discord.http.Route('POST', f'/webhooks/{webhook.id}/{webhook.token}')
    return await bot.http.request(route, json=payload)

def register_view(bot, view: discord.ui.View, message_id: int = None):
    """
    Mendaftarkan View ke listener bot secara aman (mendukung persistent view dan view ber-timeout).
    """
    if not view or view.is_finished():
        return
    try:
        if view.is_persistent():
            bot.add_view(view, message_id=message_id)
        else:
            bot._connection.store_view(view, message_id)
    except Exception:
        try:
            bot._connection.store_view(view, message_id)
        except Exception:
            pass

async def send_v2_interaction(bot, interaction: discord.Interaction, card: dict, view: discord.ui.View = None, ephemeral: bool = True):
    """
    Mengirim respon interaksi dengan komponen Container Card dan View interaktif.
    Aman dari double-acknowledgement (HTTP 40060) dan mendukung fallback.
    """
    components = [card]
    if view:
        components.extend(view.to_components())
        
    # Jika interaksi telah diakui sebelumnya (misal sudah di-defer), kirim melalui webhook followup
    if interaction.response.is_done():
        payload = {
            "flags": 32768 | (64 if ephemeral else 0),
            "components": components
        }
        app_id = getattr(bot, "application_id", None) or (bot.user.id if bot.user else None)
        if app_id:
            route = discord.http.Route(
                'POST',
                '/webhooks/{application_id}/{interaction_token}',
                application_id=app_id,
                interaction_token=interaction.token
            )
            try:
                resp = await bot.http.request(route, json=payload)
                if view and not view.is_finished():
                    register_view(bot, view, message_id=int(resp["id"]) if resp and "id" in resp else None)
                return resp
            except Exception as e:
                print(f"Failed to send layout followup: {e}")

        # Fallback followup biasa
        desc = ""
        for c in card.get("components", []):
            if c.get("type") == 10:
                desc += c.get("content", "")
        embed = discord.Embed(description=desc, color=card.get("accent_color", 0x3498db))
        try:
            if view:
                return await interaction.followup.send(embed=embed, view=view, ephemeral=ephemeral)
            else:
                return await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        except Exception as e:
            print(f"Fallback followup.send failed: {e}")
            return None

    # Respon interaksi baru (Initial Callback)
    payload = {
        "type": 4,
        "data": {
            "flags": 32768 | (64 if ephemeral else 0),
            "components": components
        }
    }
    route = discord.http.Route(
        'POST',
        '/interactions/{interaction_id}/{interaction_token}/callback',
        interaction_id=interaction.id,
        interaction_token=interaction.token
    )
    
    request_success = False
    resp = None
    try:
        resp = await bot.http.request(route, json=payload)
        request_success = True
    except Exception as e:
        print(f"Failed to send layout interaction via HTTP: {e}")

    if request_success:
        try:
            interaction.response._response_type = discord.InteractionResponseType.channel_message
        except Exception:
            pass
        if view and not view.is_finished():
            try:
                register_view(bot, view)
            except Exception:
                pass
        return resp

    # Fallback hanya jika HTTP callback belum diterima dan response belum selesai
    if not interaction.response.is_done():
        desc = ""
        for c in card.get("components", []):
            if c.get("type") == 10:
                desc += c.get("content", "")
        embed = discord.Embed(description=desc, color=card.get("accent_color", 0x3498db))
        try:
            if view:
                return await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
            else:
                return await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
        except Exception as e:
            print(f"Fallback send_message failed: {e}")
            return None

async def edit_v2_message(bot, channel_id: int, message_id: int, components: list, files: list = None):
    """
    Mengedit pesan layout menggunakan HTTP request mentah dengan parameter route yang benar.
    """
    route = discord.http.Route(
        'PATCH',
        '/channels/{channel_id}/messages/{message_id}',
        channel_id=channel_id,
        message_id=message_id
    )
    
    payload = {
        "components": components
    }
    
    try:
        if files:
            return await bot.http.request(route, payload=payload, files=files)
        else:
            return await bot.http.request(route, json=payload)
    except Exception as e:
        print(f"Failed to edit layout: {e}")
        return None

async def setup(bot):
    pass



