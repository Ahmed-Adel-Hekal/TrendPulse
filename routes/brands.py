"""routes/brands.py — Brand voice management."""
from __future__ import annotations
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth import get_current_user, escape_html
from db import (get_brands, get_brand, create_brand, update_brand,
                delete_brand, set_default_brand, get_user_settings)
from core.i18n import normalize_lang, t as _t
import ui

router = APIRouter()


def _get_lang(user):
    s = get_user_settings(user["id"])
    return normalize_lang(s.get("ui_language", "en"))


@router.get("/brands", response_class=HTMLResponse)
async def brands_page(request: Request, msg: str = ""):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    lang   = _get_lang(user)
    brands = get_brands(user["id"])

    msg_html = ""
    if msg:
        msg_html = '<div class="alert alert-success mb-3">' + escape_html(msg) + "</div>"

    brand_cards = ""
    for b in brands:
        profile    = b.get("profile", {})
        is_default = b.get("is_default", 0)
        bid        = b["id"]

        default_badge = ""
        if is_default:
            default_badge = '<span class="badge badge-green" style="font-size:9px;">Default</span>'

        set_default_btn = ""
        if not is_default:
            set_default_btn = (
                '<button class="btn btn-ghost btn-sm" '
                'onclick="setDefault(\'' + escape_html(bid) + '\')">'
                "Set default</button>"
            )

        profile_items = ""
        for k, v in list(profile.items())[:6]:
            if v:
                profile_items += (
                    "<div>"
                    '<span style="color:var(--text3);">'
                    + escape_html(k.replace("_", " ").title()) + ": </span>"
                    + escape_html(str(v)[:60]) +
                    "</div>"
                )

        brand_cards += (
            '<div class="card">'
            '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;">'
            "<div>"
            '<div style="font-weight:700;font-size:15px;">' + escape_html(b["name"]) + "</div>"
            + default_badge +
            "</div>"
            '<div style="display:flex;gap:6px;">'
            + set_default_btn +
            '<a class="btn btn-ghost btn-sm" href="/brands/' + escape_html(bid) + '/edit">Edit</a>'
            '<button class="btn btn-danger btn-sm" onclick="deleteBrand(\'' + escape_html(bid) + '\')">Delete</button>'
            "</div></div>"
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;">'
            + profile_items +
            "</div></div>"
        )

    if not brands:
        brand_cards = (
            '<div class="empty-state" style="padding:60px 20px;">'
            '<div class="empty-icon">◆</div>'
            '<div class="empty-text">' + escape_html(_t(lang, "brand.no_brands")) + "</div>"
            "<div class=\"empty-sub\">Create a brand profile to personalize your content.</div>"
            '<div style="margin-top:20px;">'
            '<a class="btn btn-primary" href="/brands/new">+ ' + escape_html(_t(lang, "brand.new")) + "</a>"
            "</div></div>"
        )

    content = (
        "<div class=\"topbar\">"
        "<div><div class=\"topbar-title\">" + escape_html(_t(lang, "brand.title")) + "</div></div>"
        '<a class="btn btn-primary" href="/brands/new">+ ' + escape_html(_t(lang, "brand.new")) + "</a>"
        "</div>"
        "<div class=\"content\">"
        + msg_html +
        '<div style="display:flex;flex-direction:column;gap:16px;">' + brand_cards + "</div>"
        "</div>"
        "<script>"
        "async function deleteBrand(id) {"
        "  if (!confirm('Delete this brand? This cannot be undone.')) return;"
        "  var r = await fetch('/brands/' + id + '/delete', {method: 'POST'});"
        "  var d = await r.json();"
        "  if (d.ok) { toast('Brand deleted', 'success'); setTimeout(function(){ location.reload(); }, 600); }"
        "  else toast(d.error || 'Failed', 'error');"
        "}"
        "async function setDefault(id) {"
        "  var r = await fetch('/brands/' + id + '/default', {method: 'POST'});"
        "  var d = await r.json();"
        "  if (d.ok) { toast('Default brand set', 'success'); setTimeout(function(){ location.reload(); }, 600); }"
        "}"
        "</script>"
    )
    return HTMLResponse(ui._page(content, user, _t(lang, "brand.title"), "brands", lang))


def _brand_form_html(lang, brand=None):
    bid    = brand["id"]             if brand else ""
    p      = brand.get("profile", {}) if brand else {}
    name   = brand["name"]           if brand else ""
    action = "/brands/" + bid + "/edit" if bid else "/brands/create"

    save_lbl   = _t(lang, "action.save")
    cancel_lbl = _t(lang, "action.cancel")
    name_lbl   = _t(lang, "brand.name")
    heading    = ("Edit " + escape_html(name)) if bid else escape_html(_t(lang, "brand.new"))

    def field(key, label, ftype, val):
        val_s = escape_html(str(val))
        if ftype == "color":
            return (
                '<div class="form-group">'
                '<label class="form-label">' + escape_html(label) + "</label>"
                '<div style="display:flex;gap:10px;align-items:center;">'
                '<input type="color" name="' + key + '" value="' + val_s + '" '
                'style="width:48px;height:36px;border:none;background:none;cursor:pointer;border-radius:4px;"/>'
                '<span style="font-family:var(--mono);font-size:11px;color:var(--text3);">' + escape_html(label) + "</span>"
                "</div></div>"
            )
        if ftype == "textarea":
            return (
                '<div class="form-group">'
                '<label class="form-label">' + escape_html(label) + "</label>"
                '<textarea class="form-textarea" name="' + key + '" style="min-height:70px;">'
                + val_s + "</textarea></div>"
            )
        return (
            '<div class="form-group">'
            '<label class="form-label">' + escape_html(label) + "</label>"
            '<input class="form-input" name="' + key + '" value="' + val_s + '"/>'
            "</div>"
        )

    fields_html = (
        field("brand_color",   "Brand Color",              "color",    p.get("brand_color", "#4f8ef7")) +
        field("brand_voice",   "Brand Voice",              "textarea", p.get("brand_voice", "")) +
        field("target_audience","Target Audience",         "textarea", p.get("target_audience", "")) +
        field("tone",          "Tone",                     "text",     p.get("tone", "")) +
        field("industry",      "Industry",                 "text",     p.get("industry", "")) +
        field("usp",           "USP / Key Message",        "textarea", p.get("usp", "")) +
        field("banned_words",  "Banned Words (comma-sep)", "text",     p.get("banned_words", ""))
    )

    return (
        '<div class="topbar">'
        '<div><div class="topbar-title">' + heading + "</div></div>"
        '<a class="btn btn-ghost" href="/brands">&larr; Back</a>'
        "</div>"
        '<div class="content">'
        '<div class="card" style="max-width:600px;">'
        '<form method="post" action="' + action + '">'
        '<div class="form-group">'
        '<label class="form-label">' + escape_html(name_lbl) + " *</label>"
        '<input class="form-input" name="name" value="' + escape_html(name) + '" required placeholder="e.g. Main Brand"/>'
        "</div>"
        + fields_html +
        '<div class="flex gap-2">'
        '<button class="btn btn-primary" type="submit">' + escape_html(save_lbl) + "</button>"
        '<a class="btn btn-ghost" href="/brands">' + escape_html(cancel_lbl) + "</a>"
        "</div>"
        "</form></div></div>"
    )


@router.get("/brands/new", response_class=HTMLResponse)
async def brand_new_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    lang = _get_lang(user)
    return HTMLResponse(ui._page(_brand_form_html(lang), user, _t(lang, "brand.new"), "brands", lang))


@router.get("/brands/{bid}/edit", response_class=HTMLResponse)
async def brand_edit_page(request: Request, bid: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    lang  = _get_lang(user)
    brand = get_brand(bid, user["id"])
    if not brand:
        return RedirectResponse("/brands", status_code=303)
    title = "Edit " + brand["name"]
    return HTMLResponse(ui._page(_brand_form_html(lang, brand), user, title, "brands", lang))


@router.post("/brands/create")
async def brand_create(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    form    = await request.form()
    name    = str(form.get("name", "")).strip()
    if not name:
        return RedirectResponse("/brands/new", status_code=303)
    profile = {k: str(v).strip() for k, v in form.items() if k != "name" and str(v).strip()}
    create_brand(user["id"], name, profile)
    return RedirectResponse("/brands?msg=Brand+created", status_code=303)


@router.post("/brands/{bid}/edit")
async def brand_update(request: Request, bid: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    form    = await request.form()
    name    = str(form.get("name", "")).strip()
    if not name:
        return RedirectResponse("/brands/" + bid + "/edit", status_code=303)
    profile = {k: str(v).strip() for k, v in form.items() if k != "name" and str(v).strip()}
    update_brand(bid, user["id"], name, profile)
    return RedirectResponse("/brands?msg=Brand+updated", status_code=303)


@router.post("/brands/{bid}/delete")
async def brand_delete(request: Request, bid: str):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    delete_brand(bid, user["id"])
    return JSONResponse({"ok": True})


@router.post("/brands/{bid}/default")
async def brand_set_default(request: Request, bid: str):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    set_default_brand(bid, user["id"])
    return JSONResponse({"ok": True})
