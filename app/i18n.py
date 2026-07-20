from aiogram.types import CallbackQuery, Message, User


SUPPORTED_LANGS = {"ru", "en", "it"}
DEFAULT_LANG = "ru"


BUTTON_LABELS = {
    "front": {"ru": "Фронт", "en": "Front", "it": "Fronte"},
    "remove_front": {"ru": "Снять с фронта", "en": "Leave front", "it": "Togli dal fronte"},
    "blur": {"ru": "Блюр", "en": "Blur", "it": "Blur"},
    "info": {"ru": "Инфо о фронте", "en": "Front info", "it": "Info fronte"},
    "directory": {"ru": "Справочник", "en": "Directory", "it": "Elenco"},
    "notifications": {"ru": "Оповещения", "en": "Notifications", "it": "Notifiche"},
    "history": {"ru": "История", "en": "History", "it": "Cronologia"},
    "statistics": {"ru": "Статистика", "en": "Stats", "it": "Statistiche"},
    "add_member": {"ru": "Управление личностями", "en": "Manage members", "it": "Gestione membri"},
}


TEXTS = {
    "input_placeholder": {
        "ru": "Выберите действие",
        "en": "Choose an action",
        "it": "Scegli un'azione",
    },
    "no_name": {"ru": "Без имени", "en": "No name", "it": "Senza nome"},
    "archived_short": {"ru": "архив", "en": "archived", "it": "archivio"},
    "cancel": {"ru": "Отмена", "en": "Cancel", "it": "Annulla"},
    "cancelled": {"ru": "Отменено.", "en": "Cancelled.", "it": "Annullato."},
    "cancelled_answer": {"ru": "Отменено", "en": "Cancelled", "it": "Annullato"},
    "details_prefix": {"ru": "Подробнее", "en": "Details", "it": "Dettagli"},
    "to_directory": {"ru": "В справочник", "en": "To directory", "it": "All'elenco"},
    "search_by_name": {"ru": "Поиск по имени", "en": "Search by name", "it": "Cerca per nome"},
    "categories": {"ru": "Категории", "en": "Categories", "it": "Categorie"},
    "all_members": {"ru": "Все личности", "en": "All members", "it": "Tutti i membri"},
    "add_to_front": {"ru": "Добавить на фронт", "en": "Add to front", "it": "Aggiungi al fronte"},
    "replace_front": {"ru": "Заменить фронт", "en": "Replace front", "it": "Sostituisci fronte"},
    "back": {"ru": "Назад", "en": "Back", "it": "Indietro"},
    "next": {"ru": "Дальше", "en": "Next", "it": "Avanti"},
    "up": {"ru": "Выше", "en": "Up", "it": "Su"},
    "back_to_choice": {"ru": "Назад к выбору", "en": "Back to choice", "it": "Torna alla scelta"},
    "unnamed_category": {"ru": "Без названия", "en": "Untitled", "it": "Senza nome"},
    "members_here": {
        "ru": "Личности здесь и ниже: {count}",
        "en": "Members here and below: {count}",
        "it": "Membri qui e sotto: {count}",
    },
    "done_count": {"ru": "Готово ({count})", "en": "Done ({count})", "it": "Fatto ({count})"},
    "done": {"ru": "Готово", "en": "Done", "it": "Fatto"},
    "skip_year": {"ru": "Пропустить год", "en": "Skip year", "it": "Salta anno"},
    "skip_role": {"ru": "Пропустить роль", "en": "Skip role", "it": "Salta ruolo"},
    "skip_categories": {"ru": "Пропустить категории", "en": "Skip categories", "it": "Salta categorie"},
    "add_category": {"ru": "Добавить категорию", "en": "Add category", "it": "Aggiungi categoria"},
    "remove_category": {"ru": "Убрать из выбранных", "en": "Remove from selected", "it": "Rimuovi dalla selezione"},
    "open_children": {"ru": "Открыть вложенные", "en": "Open children", "it": "Apri sottocategorie"},
    "new_member": {"ru": "Новая личность", "en": "New member", "it": "Nuovo membro"},
    "import_florality": {"ru": "Импорт из Florality", "en": "Import from Florality", "it": "Importa da Florality"},
    "download_florality_avatars": {
        "ru": "Загрузить аватары из Florality",
        "en": "Download Florality avatars",
        "it": "Scarica avatar da Florality",
    },
    "download_florality_categories": {
        "ru": "Загрузить категории из Florality",
        "en": "Download Florality categories",
        "it": "Scarica categorie da Florality",
    },
    "continue_florality_categories": {
        "ru": "Продолжить загрузку категорий",
        "en": "Continue category download",
        "it": "Continua il download delle categorie",
    },
    "delete_member": {"ru": "Удалить личность", "en": "Delete member", "it": "Elimina membro"},
    "export_json": {"ru": "Экспорт JSON", "en": "Export JSON", "it": "Esporta JSON"},
    "pronouns": {"ru": "Местоимения", "en": "Pronouns", "it": "Pronomi"},
    "not_specified": {"ru": "не указаны", "en": "not specified", "it": "non specificati"},
    "not_specified_f": {"ru": "не указана", "en": "not specified", "it": "non specificato"},
    "birth_year": {"ru": "Год рождения", "en": "Year of birth", "it": "Anno di nascita"},
    "role": {"ru": "Роль", "en": "Role", "it": "Ruolo"},
    "archive_yes": {"ru": "Архив: да", "en": "Archived: yes", "it": "Archivio: si"},
    "front_blur": {"ru": "блюр", "en": "blur", "it": "blur"},
    "front_status": {"ru": "фронт - {names}", "en": "front - {names}", "it": "fronte - {names}"},
    "admin_start": {
        "ru": "Вы админ. Доступно управление фронтом, справочник и управление личностями.\nВ базе личностей: {count}.",
        "en": "You are an admin. Front controls, directory, and member management are available.\nMembers in database: {count}.",
        "it": "Sei admin. Sono disponibili gestione del fronte, elenco e gestione membri.\nMembri nel database: {count}.",
    },
    "user_start": {
        "ru": "Вам доступны информация о фронте, справочник, история и оповещения.\nВ базе личностей: {count}.",
        "en": "You can use front info, directory, history, and notifications.\nMembers in database: {count}.",
        "it": "Puoi usare info fronte, elenco, cronologia e notifiche.\nMembri nel database: {count}.",
    },
    "buttons_updated": {"ru": "Кнопки обновлены.", "en": "Buttons updated.", "it": "Pulsanti aggiornati."},
    "admin_only": {
        "ru": "Управление фронтом доступно только админам.",
        "en": "Front management is only available to admins.",
        "it": "La gestione del fronte e disponibile solo agli admin.",
    },
    "enter_name": {
        "ru": "Введите имя или часть имени личности:",
        "en": "Enter a member name or part of it:",
        "it": "Inserisci il nome o una parte del nome:",
    },
    "enter_some_name": {
        "ru": "Введите хотя бы часть имени.",
        "en": "Enter at least part of a name.",
        "it": "Inserisci almeno una parte del nome.",
    },
    "nothing_found": {
        "ru": "Ничего не найдено. Попробуйте другой кусок имени.",
        "en": "Nothing found. Try another part of the name.",
        "it": "Nessun risultato. Prova un'altra parte del nome.",
    },
    "choose_front": {
        "ru": "Выберите личность для постановки на фронт:",
        "en": "Choose a member to put in front:",
        "it": "Scegli chi mettere al fronte:",
    },
    "no_front": {
        "ru": "Сейчас: блюр. На фронте никого нет.",
        "en": "Now: blur. Nobody is in front.",
        "it": "Ora: blur. Nessuno e al fronte.",
    },
    "who_remove": {"ru": "Кого снять с фронта?", "en": "Who should leave front?", "it": "Chi togliere dal fronte?"},
    "front_cleared_event": {"ru": "Фронт очищен", "en": "Front cleared", "it": "Fronte svuotato"},
    "front_cleared_status": {
        "ru": "Фронт очищен. Статус: блюр.",
        "en": "Front cleared. Status: blur.",
        "it": "Fronte svuotato. Stato: blur.",
    },
    "not_enough_rights": {"ru": "Недостаточно прав", "en": "Not enough rights", "it": "Permessi insufficienti"},
    "member_not_found": {"ru": "Личность не найдена", "en": "Member not found", "it": "Membro non trovato"},
    "ready": {"ru": "Готово", "en": "Done", "it": "Fatto"},
    "front_added_event": {"ru": "На фронт: {name}", "en": "In front: {name}", "it": "Al fronte: {name}"},
    "front_added": {"ru": "Поставлено на фронт: {name}\n{status}", "en": "Put in front: {name}\n{status}", "it": "Messo al fronte: {name}\n{status}"},
    "already_front": {"ru": "{name} уже на фронте.\n{status}", "en": "{name} is already in front.\n{status}", "it": "{name} e gia al fronte.\n{status}"},
    "front_replaced_event": {"ru": "Фронт заменён: {name}", "en": "Front replaced: {name}", "it": "Fronte sostituito: {name}"},
    "front_replaced": {"ru": "Фронт заменён: {name}\n{status}", "en": "Front replaced: {name}\n{status}", "it": "Fronte sostituito: {name}\n{status}"},
    "front_removed_event": {"ru": "{name} снят с фронта", "en": "{name} left front", "it": "{name} ha lasciato il fronte"},
    "front_removed": {"ru": "{name} снят с фронта\n{status}", "en": "{name} left front\n{status}", "it": "{name} ha lasciato il fronte\n{status}"},
    "not_in_front": {"ru": "{name} сейчас не на фронте.\n{status}", "en": "{name} is not in front now.\n{status}", "it": "{name} non e al fronte ora.\n{status}"},
    "front_changed_florality_event": {
        "ru": "Фронт изменён во Florality",
        "en": "Front changed in Florality",
        "it": "Fronte cambiato in Florality",
    },
    "admin_front_check_reminder": {
        "ru": "Напоминание: проверьте, актуален ли текущий фронт.\n\nСейчас: {status}",
        "en": "Reminder: please check whether the current front is still accurate.\n\nCurrent status: {status}",
        "it": "Promemoria: controlla se il fronte attuale è ancora corretto.\n\nStato attuale: {status}",
    },
    "history_title": {"ru": "История фронта:", "en": "Front history:", "it": "Cronologia fronte:"},
    "history_empty": {
        "ru": "История пока пустая. Новые изменения фронта начнут сохраняться с этого обновления.",
        "en": "History is empty so far. New front changes will be saved from this update.",
        "it": "La cronologia e vuota per ora. I nuovi cambi del fronte saranno salvati da questo aggiornamento.",
    },
    "stats_title": {"ru": "Статистика за {days} дней:", "en": "Stats for {days} days:", "it": "Statistiche per {days} giorni:"},
    "stats_changes": {"ru": "Изменений фронта: {count}", "en": "Front changes: {count}", "it": "Cambi fronte: {count}"},
    "stats_unique": {"ru": "Уникальных фронтеров: {count}", "en": "Unique fronters: {count}", "it": "Fronter unici: {count}"},
    "stats_blur": {"ru": "Блюров: {count}", "en": "Blur events: {count}", "it": "Eventi blur: {count}"},
    "stats_top": {"ru": "Чаще всего появлялись:", "en": "Most frequent:", "it": "Piu frequenti:"},
    "stats_distribution": {
        "ru": "Доля фронта:",
        "en": "Front share:",
        "it": "Quota fronte:",
    },
    "stats_busiest_day": {"ru": "Самый активный день: {day} ({count})", "en": "Busiest day: {day} ({count})", "it": "Giorno piu attivo: {day} ({count})"},
    "stats_last_change": {"ru": "Последнее изменение: {time}", "en": "Last change: {time}", "it": "Ultimo cambio: {time}"},
    "directory_home": {
        "ru": "Справочник: выберите способ просмотра.",
        "en": "Directory: choose how to browse.",
        "it": "Elenco: scegli come navigare.",
    },
    "found_count": {"ru": "Найдено вариантов: {count}", "en": "Found matches: {count}", "it": "Risultati trovati: {count}"},
    "shown_range": {"ru": "Показано {start}-{end} из {total}", "en": "Showing {start}-{end} of {total}", "it": "Mostrati {start}-{end} di {total}"},
    "category_title": {"ru": "Категория", "en": "Category", "it": "Categoria"},
    "child_categories": {"ru": "Вложенных категорий: {count}", "en": "Child categories: {count}", "it": "Sottocategorie: {count}"},
    "notifications_on": {
        "ru": "Оповещения о смене фронта включены.",
        "en": "Front change notifications are on.",
        "it": "Le notifiche sui cambi del fronte sono attive.",
    },
    "notifications_off": {
        "ru": "Оповещения о смене фронта выключены.",
        "en": "Front change notifications are off.",
        "it": "Le notifiche sui cambi del fronte sono disattivate.",
    },
    "add_menu": {"ru": "Управление личностями:", "en": "Member management:", "it": "Gestione membri:"},
    "florality_not_configured": {
        "ru": "Florality не настроен: добавьте FLORALITY_API_TOKEN в .env.",
        "en": "Florality is not configured: add FLORALITY_API_TOKEN to .env.",
        "it": "Florality non e configurato: aggiungi FLORALITY_API_TOKEN in .env.",
    },
    "florality_import_started": {
        "ru": "Проверка Florality запущена...",
        "en": "Florality check started...",
        "it": "Controllo Florality avviato...",
    },
    "florality_avatar_sync_started": {
        "ru": "Начинаю последовательную загрузку аватаров из Florality. Полный проход может занять несколько минут...",
        "en": "Starting sequential Florality avatar download. A full pass may take several minutes...",
        "it": "Avvio il download sequenziale degli avatar Florality. Un passaggio completo può richiedere alcuni minuti...",
    },
    "florality_avatar_sync_progress": {
        "ru": "Загружаю аватары из Florality...\n\nЗагружено: {downloaded}/{total}\nОшибок: {failed}\nОсталось попыток: {remaining}\n\nПродолжаю автоматически, API опрашивается последовательно.",
        "en": "Downloading Florality avatars...\n\nDownloaded: {downloaded}/{total}\nFailures: {failed}\nAttempts remaining: {remaining}\n\nContinuing automatically with sequential API requests.",
        "it": "Scarico gli avatar Florality...\n\nScaricati: {downloaded}/{total}\nErrori: {failed}\nTentativi rimanenti: {remaining}\n\nContinuo automaticamente con richieste API sequenziali.",
    },
    "florality_avatar_sync_done": {
        "ru": "Загрузка аватаров завершена.\n\nЗагружены:\n{downloaded}\n\nОшибки:\n{failed}\n\nУже были: {existing}\nБез аватара во Florality: {no_avatar}\nНеоднозначные совпадения: {ambiguous}\nНет локальной личности: {missing_local}\nОсталось загрузить: {remaining}",
        "en": "Avatar download finished.\n\nDownloaded:\n{downloaded}\n\nFailed:\n{failed}\n\nAlready present: {existing}\nNo Florality avatar: {no_avatar}\nAmbiguous matches: {ambiguous}\nMissing local member: {missing_local}\nRemaining: {remaining}",
        "it": "Download avatar completato.\n\nScaricati:\n{downloaded}\n\nErrori:\n{failed}\n\nGia presenti: {existing}\nSenza avatar in Florality: {no_avatar}\nCorrispondenze ambigue: {ambiguous}\nMembro locale assente: {missing_local}\nRimanenti: {remaining}",
    },
    "florality_category_sync_started": {
        "ru": "Начинаю последовательную загрузку категорий Florality. Полный проход может занять несколько минут...",
        "en": "Starting sequential Florality category download. A full pass may take several minutes...",
        "it": "Avvio il download sequenziale delle categorie Florality. Un passaggio completo può richiedere alcuni minuti...",
    },
    "florality_category_sync_progress": {
        "ru": "Загружаю категории Florality...\n\nОбработано: {processed}/{matched}\nДобавлено связей: {added}\n\nПродолжаю автоматически, API опрашивается последовательно.",
        "en": "Downloading Florality categories...\n\nProcessed: {processed}/{matched}\nLinks added: {added}\n\nContinuing automatically with sequential API requests.",
        "it": "Scarico le categorie Florality...\n\nElaborati: {processed}/{matched}\nCollegamenti aggiunti: {added}\n\nContinuo automaticamente con richieste API sequenziali.",
    },
    "florality_category_sync_done": {
        "ru": "Загрузка категорий завершена.\n\nОбработано групп: {processed}\nСопоставлено групп всего: {matched}\nБез локального соответствия: {unmatched}\nДобавлено связей: {added}\n\nОбновлены личности:\n{affected}\n\nОшибки групп:\n{failed}\n\nОсталось групп: {remaining}\nБекап: {backup}",
        "en": "Category download finished.\n\nGroups processed: {processed}\nGroups matched in total: {matched}\nNo local match: {unmatched}\nLinks added: {added}\n\nUpdated members:\n{affected}\n\nFailed groups:\n{failed}\n\nGroups remaining: {remaining}\nBackup: {backup}",
        "it": "Download categorie completato.\n\nGruppi elaborati: {processed}\nGruppi abbinati totali: {matched}\nSenza corrispondenza locale: {unmatched}\nCollegamenti aggiunti: {added}\n\nMembri aggiornati:\n{affected}\n\nGruppi con errori:\n{failed}\n\nGruppi rimanenti: {remaining}\nBackup: {backup}",
    },
    "florality_import_done": {
        "ru": "Проверка Florality завершена.\n\nИмпортированы новые личности:\n{imported}\n\nИзменены во Florality:\n{changed}\n\nНе удалось импортировать:\n{missing_local}\n\nЕсть локально, нет в активном Florality:\n{missing_remote}\n\nБез изменений: {unchanged}\nПропущено (неоднозначные совпадения): {skipped}\nБекап: {backup}",
        "en": "Florality check finished.\n\nImported new members:\n{imported}\n\nChanged in Florality:\n{changed}\n\nCould not import:\n{missing_local}\n\nLocal, missing from active Florality:\n{missing_remote}\n\nUnchanged: {unchanged}\nSkipped (ambiguous matches): {skipped}\nBackup: {backup}",
        "it": "Controllo Florality completato.\n\nNuovi membri importati:\n{imported}\n\nModificati in Florality:\n{changed}\n\nImpossibile importare:\n{missing_local}\n\nLocali, assenti da Florality attivo:\n{missing_remote}\n\nSenza modifiche: {unchanged}\nSaltati (corrispondenze ambigue): {skipped}\nBackup: {backup}",
    },
    "manual_add_disabled": {
        "ru": "Ручное добавление временно отключено. Используйте импорт из Florality.",
        "en": "Manual creation is temporarily disabled. Use Florality import.",
        "it": "La creazione manuale e temporaneamente disattivata. Usa l'import da Florality.",
    },
    "manual_delete_disabled": {
        "ru": "Локальное удаление отключено. Удалите личность во Florality и запустите импорт.",
        "en": "Local deletion is disabled. Delete the member in Florality and run import.",
        "it": "L'eliminazione locale e disattivata. Elimina il membro in Florality e avvia l'import.",
    },
    "enter_new_name": {"ru": "Введите имя новой личности:", "en": "Enter the new member name:", "it": "Inserisci il nome del nuovo membro:"},
    "name_required": {"ru": "Имя обязательно. Введите имя новой личности:", "en": "Name is required. Enter the new member name:", "it": "Il nome e obbligatorio. Inserisci il nome:"},
    "enter_pronouns": {"ru": "Введите местоимения или «-», чтобы пропустить:", "en": "Enter pronouns or '-' to skip:", "it": "Inserisci i pronomi o '-' per saltare:"},
    "enter_description": {"ru": "Введите описание или «-», чтобы пропустить:", "en": "Enter a description or '-' to skip:", "it": "Inserisci una descrizione o '-' per saltare:"},
    "choose_year": {"ru": "Выберите год рождения:", "en": "Choose year of birth:", "it": "Scegli anno di nascita:"},
    "choose_role": {"ru": "Выберите роль:", "en": "Choose role:", "it": "Scegli ruolo:"},
    "choose_categories": {
        "ru": "Выберите дополнительные категории или нажмите «Готово».",
        "en": "Choose additional categories or press Done.",
        "it": "Scegli categorie aggiuntive o premi Fatto.",
    },
    "name_lost": {"ru": "Имя потерялось, начните заново", "en": "Name was lost, start again", "it": "Nome perso, ricomincia"},
    "member_added_answer": {"ru": "Личность добавлена", "en": "Member added", "it": "Membro aggiunto"},
    "member_added": {"ru": "Личность добавлена:\n\n{brief}", "en": "Member added:\n\n{brief}", "it": "Membro aggiunto:\n\n{brief}"},
    "category_not_found": {"ru": "Категория не найдена", "en": "Category not found", "it": "Categoria non trovata"},
    "updated": {"ru": "Обновлено", "en": "Updated", "it": "Aggiornato"},
    "export_ready": {"ru": "Экспорт готов", "en": "Export ready", "it": "Esportazione pronta"},
    "export_caption": {"ru": "Экспорт текущей базы.", "en": "Current database export.", "it": "Esportazione del database corrente."},
    "delete_prompt": {"ru": "Введите имя или часть имени для удаления:", "en": "Enter a member name or part of it to delete:", "it": "Inserisci nome o parte del nome da eliminare:"},
    "choose_delete": {"ru": "Выберите личность для логического удаления:", "en": "Choose a member to logically delete:", "it": "Scegli un membro da eliminare logicamente:"},
    "delete_confirm": {"ru": "Удалить логически: {name}?", "en": "Logically delete {name}?", "it": "Eliminare logicamente {name}?"},
    "delete_confirm_button": {"ru": "Удалить", "en": "Delete", "it": "Elimina"},
    "deleted": {"ru": "Личность логически удалена: {name}", "en": "Member logically deleted: {name}", "it": "Membro eliminato logicamente: {name}"},
}


def normalize_lang(language_code: str | None) -> str:
    if not language_code:
        return DEFAULT_LANG
    lang = language_code.casefold().split("-", 1)[0].split("_", 1)[0]
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def lang_from_user(user: User | None) -> str:
    return normalize_lang(user.language_code if user else None)


def lang_from_message(message: Message) -> str:
    return lang_from_user(message.from_user)


def lang_from_callback(callback: CallbackQuery) -> str:
    return lang_from_user(callback.from_user)


def t(key: str, lang: str = DEFAULT_LANG, **kwargs: object) -> str:
    values = TEXTS[key]
    text = values.get(lang) or values[DEFAULT_LANG]
    return text.format(**kwargs)


def button_text(key: str, lang: str = DEFAULT_LANG) -> str:
    values = BUTTON_LABELS[key]
    return values.get(lang) or values[DEFAULT_LANG]


def is_button_text(text: str | None, key: str) -> bool:
    if text is None:
        return False
    return text in set(BUTTON_LABELS[key].values())


def all_button_texts() -> set[str]:
    result: set[str] = set()
    for values in BUTTON_LABELS.values():
        result.update(values.values())
    return result
