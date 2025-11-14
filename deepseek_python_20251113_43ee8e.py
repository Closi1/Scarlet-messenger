import socket
import threading
import struct
import time
import hashlib
import sqlite3
import json
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import select
import queue
import re
import os
import pickle


class UserManager:
    """Менеджер для запоминания пользователей"""
    
    def __init__(self):
        self.users_file = 'remembered_users.pkl'
        self.remembered_users = self.load_remembered_users()
    
    def load_remembered_users(self):
        """Загрузка запомненных пользователей"""
        try:
            if os.path.exists(self.users_file):
                with open(self.users_file, 'rb') as f:
                    return pickle.load(f)
        except Exception as e:
            print(f"Error loading remembered users: {e}")
        return {}
    
    def save_remembered_users(self):
        """Сохранение запомненных пользователей"""
        try:
            with open(self.users_file, 'wb') as f:
                pickle.dump(self.remembered_users, f)
        except Exception as e:
            print(f"Error saving remembered users: {e}")
    
    def remember_user(self, ip, username, password_hash=None):
        """Запомнить пользователя по IP"""
        self.remembered_users[ip] = {
            'username': username,
            'password_hash': password_hash,  # Сохраняем хеш пароля для автоматического входа
            'timestamp': datetime.now().isoformat(),
            'auto_login': True if password_hash else False
        }
        self.save_remembered_users()
    
    def get_remembered_user(self, ip):
        """Получить запомненного пользователя по IP"""
        return self.remembered_users.get(ip)
    
    def forget_user(self, ip):
        """Забыть пользователя по IP"""
        if ip in self.remembered_users:
            del self.remembered_users[ip]
            self.save_remembered_users()
    
    def update_auto_login(self, ip, enable=True):
        """Обновить настройку автоматического входа"""
        if ip in self.remembered_users:
            self.remembered_users[ip]['auto_login'] = enable
            self.save_remembered_users()


class SettingsManager:
    """Менеджер настроек приложения"""
    
    def __init__(self):
        self.settings_file = 'app_settings.pkl'
        self.settings = self.load_settings()
    
    def load_settings(self):
        """Загрузка настроек"""
        default_settings = {
            'theme': 'dark',
            'auto_login': True,
            'notifications': True,
            'sound_effects': True,
            'message_history_limit': 1000,
            'font_size': 11,
            'start_minimized': False,
            'show_online_status': True
        }
        
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'rb') as f:
                    loaded_settings = pickle.load(f)
                    # Объединяем с настройками по умолчанию
                    default_settings.update(loaded_settings)
        except Exception as e:
            print(f"Error loading settings: {e}")
        
        return default_settings
    
    def save_settings(self):
        """Сохранение настроек"""
        try:
            with open(self.settings_file, 'wb') as f:
                pickle.dump(self.settings, f)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def get(self, key, default=None):
        """Получить значение настройки"""
        return self.settings.get(key, default)
    
    def set(self, key, value):
        """Установить значение настройки"""
        self.settings[key] = value
        self.save_settings()


class DatabaseManager:
    def __init__(self):
        self.conn = sqlite3.connect('messenger.db', check_same_thread=False)
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        cursor = self.conn.cursor()

        tables = {
            'users': '''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''',
            'user_profiles': '''
                CREATE TABLE IF NOT EXISTS user_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    display_name TEXT,
                    status_text TEXT DEFAULT 'В сети',
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (username) REFERENCES users (username)
                )
            ''',
            'contacts': '''
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    contact_username TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(user_id, contact_username)
                )
            ''',
            'messages': '''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    receiver TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    message_text TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_read BOOLEAN DEFAULT FALSE
                )
            ''',
            'group_chats': '''
                CREATE TABLE IF NOT EXISTS group_chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    creator TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''',
            'group_members': '''
                CREATE TABLE IF NOT EXISTS group_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    username TEXT NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id) REFERENCES group_chats (id),
                    UNIQUE(group_id, username)
                )
            '''
        }

        for table_name, table_sql in tables.items():
            cursor.execute(table_sql)

        self.conn.commit()

    def register_user(self, username, password):
        """Регистрация нового пользователя"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        try:
            self.conn.execute(
                'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                (username, password_hash)
            )
            # Создаем профиль пользователя
            self.conn.execute(
                'INSERT INTO user_profiles (username, display_name) VALUES (?, ?)',
                (username, username)
            )
            self.conn.commit()
            return True, password_hash
        except sqlite3.IntegrityError:
            return False, None

    def authenticate_user(self, username, password):
        """Аутентификация пользователя"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        cursor = self.conn.execute(
            'SELECT id FROM users WHERE username = ? AND password_hash = ?',
            (username, password_hash)
        )

        return cursor.fetchone() is not None, password_hash

    def authenticate_with_hash(self, username, password_hash):
        """Аутентификация по хешу пароля"""
        cursor = self.conn.execute(
            'SELECT id FROM users WHERE username = ? AND password_hash = ?',
            (username, password_hash)
        )

        return cursor.fetchone() is not None

    def update_user_profile(self, username, display_name=None, status_text=None):
        """Обновление профиля пользователя"""
        try:
            if display_name:
                self.conn.execute(
                    'UPDATE user_profiles SET display_name = ? WHERE username = ?',
                    (display_name, username)
                )
            if status_text:
                self.conn.execute(
                    'UPDATE user_profiles SET status_text = ? WHERE username = ?',
                    (status_text, username)
                )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error updating profile: {e}")
            return False

    def get_user_profile(self, username):
        """Получение профиля пользователя"""
        cursor = self.conn.execute(
            'SELECT username, display_name, status_text, last_seen FROM user_profiles WHERE username = ?',
            (username,)
        )
        row = cursor.fetchone()
        if row:
            return {
                'username': row[0],
                'display_name': row[1],
                'status_text': row[2],
                'last_seen': row[3]
            }
        return None

    def change_username(self, old_username, new_username):
        """Изменение имени пользователя"""
        try:
            # Обновляем имя пользователя во всех связанных таблицах
            self.conn.execute('BEGIN TRANSACTION')
            
            # Обновляем в таблице users
            self.conn.execute(
                'UPDATE users SET username = ? WHERE username = ?',
                (new_username, old_username)
            )
            
            # Обновляем в таблице user_profiles
            self.conn.execute(
                'UPDATE user_profiles SET username = ? WHERE username = ?',
                (new_username, old_username)
            )
            
            # Обновляем в таблице messages
            self.conn.execute(
                'UPDATE messages SET sender = ? WHERE sender = ?',
                (new_username, old_username)
            )
            self.conn.execute(
                'UPDATE messages SET receiver = ? WHERE receiver = ?',
                (new_username, old_username)
            )
            
            # Обновляем в таблице contacts
            self.conn.execute(
                'UPDATE contacts SET contact_username = ? WHERE contact_username = ?',
                (new_username, old_username)
            )
            
            # Обновляем в таблице group_chats
            self.conn.execute(
                'UPDATE group_chats SET creator = ? WHERE creator = ?',
                (new_username, old_username)
            )
            
            # Обновляем в таблице group_members
            self.conn.execute(
                'UPDATE group_members SET username = ? WHERE username = ?',
                (new_username, old_username)
            )
            
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            self.conn.rollback()
            return False
        except Exception as e:
            self.conn.rollback()
            print(f"Error changing username: {e}")
            return False

    def add_contact(self, username, contact_username):
        """Добавление контакта"""
        # Проверяем существование пользователя
        cursor = self.conn.execute('SELECT id FROM users WHERE username = ?', (contact_username,))
        if not cursor.fetchone():
            return False

        try:
            self.conn.execute(
                'INSERT INTO contacts (user_id, contact_username) VALUES ((SELECT id FROM users WHERE username = ?), ?)',
                (username, contact_username)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def create_group_chat(self, name, creator):
        """Создание группового чата"""
        try:
            cursor = self.conn.execute(
                'INSERT INTO group_chats (name, creator) VALUES (?, ?)',
                (name, creator)
            )
            group_id = cursor.lastrowid

            # Добавляем создателя в участники
            self.conn.execute(
                'INSERT INTO group_members (group_id, username) VALUES (?, ?)',
                (group_id, creator)
            )

            self.conn.commit()
            return group_id
        except sqlite3.IntegrityError:
            return None

    def add_user_to_group(self, group_id, username):
        """Добавление пользователя в групповой чат"""
        try:
            self.conn.execute(
                'INSERT INTO group_members (group_id, username) VALUES (?, ?)',
                (group_id, username)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_user_groups(self, username):
        """Получение групповых чатов пользователя"""
        cursor = self.conn.execute('''
            SELECT gc.id, gc.name, gc.creator 
            FROM group_chats gc
            JOIN group_members gm ON gc.id = gm.group_id
            WHERE gm.username = ?
            ORDER BY gc.name
        ''', (username,))

        return [{'id': row[0], 'name': row[1], 'creator': row[2]} for row in cursor.fetchall()]

    def get_contacts(self, username):
        """Получение списка контактов"""
        cursor = self.conn.execute('''
            SELECT contact_username FROM contacts 
            WHERE user_id = (SELECT id FROM users WHERE username = ?)
            ORDER BY contact_username
        ''', (username,))

        return [row[0] for row in cursor.fetchall()]

    def save_message(self, sender, receiver, message_type, message_text):
        """Сохранение сообщения в базу данных"""
        self.conn.execute('''
            INSERT INTO messages (sender, receiver, message_type, message_text)
            VALUES (?, ?, ?, ?)
        ''', (sender, receiver, message_type, message_text))
        self.conn.commit()

    def get_message_history(self, user1, user2, message_type='private', limit=1000):
        """Получение истории сообщений"""
        if message_type == 'group':
            cursor = self.conn.execute('''
                SELECT sender, message_text, timestamp 
                FROM messages 
                WHERE receiver = ? AND message_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (user2, message_type, limit))
        else:
            cursor = self.conn.execute('''
                SELECT sender, message_text, timestamp 
                FROM messages 
                WHERE ((sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?))
                AND message_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (user1, user2, user2, user1, message_type, limit))

        messages = cursor.fetchall()
        return list(reversed(messages))

    def get_all_messages(self, username, limit=500):
        """Получение всех сообщений пользователя"""
        cursor = self.conn.execute('''
            SELECT sender, receiver, message_type, message_text, timestamp 
            FROM messages 
            WHERE sender = ? OR receiver = ? OR receiver IN (
                SELECT name FROM group_chats WHERE id IN (
                    SELECT group_id FROM group_members WHERE username = ?
                )
            )
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (username, username, username, limit))

        return list(reversed(cursor.fetchall()))

    def __del__(self):
        """Закрытие соединения с БД при уничтожении объекта"""
        if hasattr(self, 'conn'):
            self.conn.close()


class MulticastMessenger:
    def __init__(self, username, multicast_group='224.1.1.1', port=5007):
        self.username = username
        self.multicast_group = multicast_group
        self.port = port
        self.running = True
        self.contacts = {}
        self.groups = {}

        # База данных
        self.db = DatabaseManager()

        # Менеджер настроек
        self.settings = SettingsManager()

        # Очередь для сообщений GUI
        self.message_queue = queue.Queue()

        # Инициализация сокетов
        self.init_sockets()

        # Загрузка контактов и групп
        self.load_contacts()
        self.load_groups()

    def init_sockets(self):
        """Инициализация сетевых сокетов"""
        # Multicast сокет для группового чата
        self.multicast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.multicast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.multicast_sock.settimeout(1.0)
        self.join_multicast_group()

        # TCP сервер для личных сообщений
        self.tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_server.settimeout(1.0)
        self.tcp_server.bind(('0.0.0.0', 0))
        self.tcp_port = self.tcp_server.getsockname()[1]
        self.tcp_server.listen(5)

        # Клиентские TCP соединения
        self.client_sockets = []

    def join_multicast_group(self):
        """Присоединение к multicast группе"""
        try:
            group = socket.inet_aton(self.multicast_group)
            mreq = struct.pack('4sL', group, socket.INADDR_ANY)
            self.multicast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self.multicast_sock.bind(('', self.port))
        except Exception as e:
            print(f"Multicast error: {e}")

    def load_contacts(self):
        """Загрузка контактов из базы данных"""
        contacts = self.db.get_contacts(self.username)
        for contact in contacts:
            self.contacts[contact] = {'online': False, 'ip': None, 'port': None}

    def load_groups(self):
        """Загрузка групповых чатов"""
        groups = self.db.get_user_groups(self.username)
        for group in groups:
            self.groups[f"GROUP_{group['id']}"] = {
                'name': group['name'],
                'creator': group['creator'],
                'online': True
            }

    def broadcast_presence(self):
        """Рассылка информации о своем присутствии"""
        while self.running:
            try:
                presence_msg = {
                    'type': 'presence',
                    'username': self.username,
                    'port': self.tcp_port,
                    'action': 'online'
                }

                self.multicast_sock.sendto(
                    json.dumps(presence_msg).encode('utf-8'),
                    (self.multicast_group, self.port)
                )
            except Exception as e:
                print(f"Presence broadcast error: {e}")

            time.sleep(10)

    def listen_multicast(self):
        """Прослушивание multicast сообщений"""
        while self.running:
            try:
                data, addr = self.multicast_sock.recvfrom(1024)
                message = json.loads(data.decode('utf-8'))

                if message['type'] == 'presence':
                    self.handle_presence(message, addr[0])
                elif message['type'] == 'group_message':
                    self.handle_group_message(message)

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Multicast listen error: {e}")

    def handle_presence(self, message, ip):
        """Обработка сообщений о присутствии"""
        username = message['username']

        if username != self.username and username in self.contacts:
            self.contacts[username]['online'] = (message['action'] == 'online')
            self.contacts[username]['ip'] = ip
            self.contacts[username]['port'] = message['port']

            self.message_queue.put(('update_contacts', None))

    def handle_group_message(self, message):
        """Обработка групповых сообщений"""
        if message['sender'] != self.username:
            # Сохраняем в базу данных
            self.db.save_message(
                message['sender'],
                message['group_id'],
                'group',
                message['text']
            )

            # Отправляем в очередь для GUI
            self.message_queue.put(('group_message', message))

    def send_group_message(self, group_id, text):
        """Отправка группового сообщения"""
        try:
            message = {
                'type': 'group_message',
                'sender': self.username,
                'group_id': group_id,
                'text': text,
                'timestamp': datetime.now().isoformat()
            }

            self.multicast_sock.sendto(
                json.dumps(message).encode('utf-8'),
                (self.multicast_group, self.port)
            )

            # Сохраняем свое сообщение
            self.db.save_message(self.username, group_id, 'group', text)
            return True
        except Exception as e:
            print(f"Send group message error: {e}")
            return False

    def listen_tcp(self):
        """Прослушивание TCP соединений для личных сообщений"""
        while self.running:
            try:
                read_sockets = [self.tcp_server] + self.client_sockets
                read_sockets, _, _ = select.select(read_sockets, [], [], 1.0)

                for sock in read_sockets:
                    if sock == self.tcp_server:
                        try:
                            client_socket, addr = self.tcp_server.accept()
                            client_socket.settimeout(1.0)
                            self.client_sockets.append(client_socket)
                        except socket.timeout:
                            continue
                    else:
                        try:
                            data = sock.recv(1024)
                            if data:
                                message = json.loads(data.decode('utf-8'))
                                self.handle_private_message(message)
                            else:
                                sock.close()
                                self.client_sockets.remove(sock)
                        except (socket.timeout, ConnectionError):
                            if sock in self.client_sockets:
                                sock.close()
                                self.client_sockets.remove(sock)

            except Exception as e:
                if self.running:
                    print(f"TCP listen error: {e}")

    def handle_private_message(self, message):
        """Обработка личных сообщений"""
        if message['type'] == 'private_message':
            # Сохраняем в базу данных
            self.db.save_message(
                message['sender'],
                message['receiver'],
                'private',
                message['text']
            )

            # Отправляем в очередь для GUI
            self.message_queue.put(('private_message', message))

    def send_private_message(self, receiver, text):
        """Отправка личного сообщения"""
        # Всегда сохраняем сообщение в БД
        self.db.save_message(self.username, receiver, 'private', text)

        if receiver in self.contacts and self.contacts[receiver]['online']:
            try:
                message = {
                    'type': 'private_message',
                    'sender': self.username,
                    'receiver': receiver,
                    'text': text,
                    'timestamp': datetime.now().isoformat()
                }

                # Создаем отдельный поток для отправки
                thread = threading.Thread(
                    target=self._send_private_message_thread,
                    args=(receiver, message)
                )
                thread.daemon = True
                thread.start()
                return True
            except Exception as e:
                print(f"Send private message error: {e}")
                return False
        return True

    def _send_private_message_thread(self, receiver, message):
        """Поток для отправки личного сообщения"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)

            contact_ip = self.contacts[receiver]['ip']
            contact_port = self.contacts[receiver]['port']

            sock.connect((contact_ip, contact_port))
            sock.send(json.dumps(message).encode('utf-8'))
            sock.close()

        except (socket.timeout, ConnectionError):
            print(f"Timeout sending message to {receiver}")
            self.contacts[receiver]['online'] = False
            self.message_queue.put(('update_contacts', None))
        except Exception as e:
            print(f"Error sending to {receiver}: {e}")
            self.contacts[receiver]['online'] = False
            self.message_queue.put(('update_contacts', None))

    def add_contact(self, contact_username):
        """Добавление контакта"""
        if contact_username != self.username and self.db.add_contact(self.username, contact_username):
            self.contacts[contact_username] = {'online': False, 'ip': None, 'port': None}
            self.message_queue.put(('update_contacts', None))
            return True
        return False

    def create_group(self, group_name):
        """Создание группового чата"""
        group_id = self.db.create_group_chat(group_name, self.username)
        if group_id:
            self.load_groups()
            self.message_queue.put(('update_groups', None))
            return group_id
        return None

    def get_all_messages(self, limit=500):
        """Получение всех сообщений пользователя"""
        return self.db.get_all_messages(self.username, limit)

    def update_profile(self, display_name=None, status_text=None):
        """Обновление профиля пользователя"""
        return self.db.update_user_profile(self.username, display_name, status_text)

    def change_username(self, new_username):
        """Изменение имени пользователя"""
        if new_username == self.username:
            return True, "Имя не изменилось"

        success = self.db.change_username(self.username, new_username)
        if success:
            old_username = self.username
            self.username = new_username
            return True, f"Имя пользователя изменено с '{old_username}' на '{new_username}'"
        else:
            return False, "Пользователь с таким именем уже существует"

    def get_user_profile(self):
        """Получение профиля пользователя"""
        return self.db.get_user_profile(self.username)

    def process_message_queue(self):
        """Обработка очереди сообщений для GUI"""
        try:
            while True:
                msg_type, message = self.message_queue.get_nowait()

                if msg_type == 'update_contacts' and hasattr(self, 'update_contacts_callback'):
                    self.update_contacts_callback()
                elif msg_type == 'update_groups' and hasattr(self, 'update_groups_callback'):
                    self.update_groups_callback()
                elif msg_type == 'group_message' and hasattr(self, 'group_message_callback'):
                    self.group_message_callback(message)
                elif msg_type == 'private_message' and hasattr(self, 'private_message_callback'):
                    self.private_message_callback(message)

        except queue.Empty:
            pass

    def start(self):
        """Запуск всех потоков"""
        threads = [
            threading.Thread(target=self.listen_multicast),
            threading.Thread(target=self.listen_tcp),
            threading.Thread(target=self.broadcast_presence)
        ]

        for thread in threads:
            thread.daemon = True
            thread.start()

    def stop(self):
        """Остановка мессенджера"""
        self.running = False

        try:
            presence_msg = {
                'type': 'presence',
                'username': self.username,
                'port': self.tcp_port,
                'action': 'offline'
            }

            self.multicast_sock.sendto(
                json.dumps(presence_msg).encode('utf-8'),
                (self.multicast_group, self.port)
            )
        except:
            pass

        try:
            self.multicast_sock.close()
        except:
            pass

        try:
            self.tcp_server.close()
        except:
            pass

        for sock in self.client_sockets:
            try:
                sock.close()
            except:
                pass


class ModernMessengerGUI:
    def __init__(self, root, messenger):
        self.root = root
        self.messenger = messenger
        self.current_chat = 'MAIN_GROUP'
        self.current_chat_type = 'group'

        # Настройка callback'ов
        self.messenger.group_message_callback = self.handle_group_message
        self.messenger.private_message_callback = self.handle_private_message
        self.messenger.update_contacts_callback = self.update_chats_list
        self.messenger.update_groups_callback = self.update_chats_list

        # Современная цветовая схема
        self.colors = {
            'primary': '#1a1a2e',
            'secondary': '#16213e',
            'accent': '#0f3460',
            'highlight': '#e94560',
            'text_primary': '#ffffff',
            'text_secondary': '#b8b8b8',
            'success': '#00b894',
            'warning': '#fdcb6e',
            'error': '#d63031'
        }

        self.setup_ui()
        self.load_chat_history()

        # Запуск обработки очереди сообщений
        self.process_queue()

    def setup_ui(self):
        """Настройка современного графического интерфейса"""
        self.root.title(f"✨ NeoChat - {self.messenger.username}")
        self.root.geometry("1400x900")
        self.root.configure(bg=self.colors['primary'])
        self.root.minsize(1200, 800)

        # Создаем стили
        self.setup_styles()

        # Основной контейнер
        main_container = tk.Frame(self.root, bg=self.colors['primary'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Левая панель - навигация
        self.setup_sidebar(main_container)

        # Правая панель - чат
        self.setup_chat_area(main_container)

        # Фокус на поле ввода
        self.message_entry.focus_set()

    def setup_styles(self):
        """Настройка современных стилей"""
        style = ttk.Style()
        
        # Современная тема
        style.theme_use('clam')
        
        # Настраиваем стили для различных элементов
        style.configure('Modern.TFrame', background=self.colors['secondary'])
        style.configure('Nav.TButton', 
                       background=self.colors['accent'],
                       foreground=self.colors['text_primary'],
                       borderwidth=0,
                       focuscolor='none')
        
        style.map('Nav.TButton',
                 background=[('active', self.colors['highlight']),
                           ('pressed', self.colors['highlight'])])

    def setup_sidebar(self, parent):
        """Настройка боковой панели"""
        sidebar = ttk.Frame(parent, width=320, style='Modern.TFrame')
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 15))
        sidebar.pack_propagate(False)

        # Заголовок приложения
        header_frame = tk.Frame(sidebar, bg=self.colors['accent'], height=100)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)

        # Кликабельный ник пользователя
        user_profile_frame = tk.Frame(header_frame, bg=self.colors['accent'])
        user_profile_frame.pack(fill=tk.X, expand=True)

        app_logo = tk.Label(user_profile_frame, text="✨ NeoChat", 
                           font=('Segoe UI', 16, 'bold'),
                           bg=self.colors['accent'],
                           fg=self.colors['text_primary'])
        app_logo.pack(anchor='w', padx=15, pady=(15, 5))

        # Отображаемое имя пользователя (кликабельное)
        profile = self.messenger.get_user_profile()
        display_name = profile['display_name'] if profile else self.messenger.username
        
        self.user_name_label = tk.Label(
            user_profile_frame, 
            text=f"👤 {display_name}",
            font=('Segoe UI', 12, 'bold'),
            bg=self.colors['accent'],
            fg=self.colors['text_primary'],
            cursor='hand2'
        )
        self.user_name_label.pack(anchor='w', padx=15, pady=(0, 15))
        self.user_name_label.bind('<Button-1>', self.show_profile_menu)

        # Панель управления
        control_frame = tk.Frame(sidebar, bg=self.colors['secondary'], pady=15)
        control_frame.pack(fill=tk.X)

        buttons = [
            ("👥 Добавить контакт", self.add_contact_dialog),
            ("🆕 Создать группу", self.create_group_dialog),
            ("📜 История сообщений", self.show_message_history),
            ("⚙️ Настройки", self.show_settings_dialog)
        ]

        for text, command in buttons:
            btn = self.create_modern_button(control_frame, text, command)
            btn.pack(fill=tk.X, padx=15, pady=5)

        # Разделитель
        separator = tk.Frame(sidebar, height=2, bg=self.colors['accent'])
        separator.pack(fill=tk.X, pady=10)

        # Заголовок списка чатов
        chats_header = tk.Label(sidebar, text="💬 Активные чаты",
                               font=('Segoe UI', 12, 'bold'),
                               bg=self.colors['secondary'],
                               fg=self.colors['text_secondary'],
                               pady=10)
        chats_header.pack(fill=tk.X)

        # Список чатов с прокруткой
        chats_container = tk.Frame(sidebar, bg=self.colors['secondary'])
        chats_container.pack(fill=tk.BOTH, expand=True)

        # Canvas и Scrollbar для списка чатов
        self.chats_canvas = tk.Canvas(chats_container, bg=self.colors['secondary'],
                                     highlightthickness=0)
        scrollbar = ttk.Scrollbar(chats_container, orient=tk.VERTICAL,
                                 command=self.chats_canvas.yview)
        self.chats_frame = tk.Frame(self.chats_canvas, bg=self.colors['secondary'])

        self.chats_canvas.configure(yscrollcommand=scrollbar.set)
        self.chats_canvas.create_window((0, 0), window=self.chats_frame, anchor='nw')

        self.chats_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Привязываем обновление прокрутки
        self.chats_frame.bind('<Configure>', 
                             lambda e: self.chats_canvas.configure(
                                 scrollregion=self.chats_canvas.bbox('all')))

        # Обновляем список чатов
        self.update_chats_list()

    def setup_chat_area(self, parent):
        """Настройка области чата"""
        chat_container = tk.Frame(parent, bg=self.colors['primary'])
        chat_container.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Заголовок чата
        self.chat_header = tk.Frame(chat_container, bg=self.colors['accent'], height=80)
        self.chat_header.pack(fill=tk.X)
        self.chat_header.pack_propagate(False)

        self.chat_title = tk.Label(self.chat_header, text="💬 Основной чат",
                                  font=('Segoe UI', 16, 'bold'),
                                  bg=self.colors['accent'],
                                  fg=self.colors['text_primary'])
        self.chat_title.pack(expand=True)

        # Область сообщений
        messages_container = tk.Frame(chat_container, bg=self.colors['primary'])
        messages_container.pack(fill=tk.BOTH, expand=True, pady=(15, 15))

        self.messages_text = scrolledtext.ScrolledText(
            messages_container,
            wrap=tk.WORD,
            font=('Segoe UI', 11),
            bg=self.colors['secondary'],
            fg=self.colors['text_primary'],
            padx=20,
            pady=20,
            state=tk.DISABLED,
            borderwidth=0,
            relief='flat',
            highlightthickness=0
        )
        self.messages_text.pack(fill=tk.BOTH, expand=True)

        # Настройка тегов для сообщений
        self.setup_message_tags()

        # Панель ввода сообщения
        input_frame = tk.Frame(chat_container, bg=self.colors['primary'], pady=10)
        input_frame.pack(fill=tk.X)

        # Верхняя панель ввода (счетчик символов)
        input_top_frame = tk.Frame(input_frame, bg=self.colors['primary'])
        input_top_frame.pack(fill=tk.X, pady=(0, 8))

        self.char_count_label = tk.Label(input_top_frame, text="0/1000",
                                        font=('Segoe UI', 10),
                                        bg=self.colors['primary'],
                                        fg=self.colors['text_secondary'])
        self.char_count_label.pack(side=tk.RIGHT)

        # Основное поле ввода
        input_main_frame = tk.Frame(input_frame, bg=self.colors['accent'], relief='flat',
                                   borderwidth=0, padx=3, pady=3)
        input_main_frame.pack(fill=tk.X)

        self.message_entry = tk.Text(
            input_main_frame,
            height=3,
            font=('Segoe UI', 12),
            wrap=tk.WORD,
            bg=self.colors['secondary'],
            fg=self.colors['text_primary'],
            insertbackground=self.colors['highlight'],
            relief='flat',
            borderwidth=0,
            padx=15,
            pady=12
        )
        self.message_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.message_entry.bind('<KeyRelease>', self.update_char_count)
        self.message_entry.bind('<Return>', self.send_message_enter)
        self.message_entry.bind('<Shift-Return>', self.insert_newline)

        # Кнопка отправки
        send_button = tk.Button(
            input_main_frame,
            text="🚀",
            command=self.send_message,
            bg=self.colors['highlight'],
            fg=self.colors['text_primary'],
            font=('Segoe UI', 14, 'bold'),
            relief='flat',
            borderwidth=0,
            width=4,
            height=2,
            cursor='hand2'
        )
        send_button.pack(side=tk.RIGHT, padx=(10, 0))

        self.update_char_count()

    def setup_message_tags(self):
        """Настройка тегов для форматирования сообщений"""
        tags_config = {
            "own": {
                'foreground': self.colors['highlight'],
                'justify': tk.RIGHT,
                'font': ('Segoe UI', 11, 'bold'),
                'lmargin1': 100,
                'lmargin2': 100,
                'rmargin': 20
            },
            "other": {
                'foreground': self.colors['text_primary'],
                'justify': tk.LEFT,
                'font': ('Segoe UI', 11),
                'lmargin1': 20,
                'lmargin2': 20,
                'rmargin': 100
            },
            "system": {
                'foreground': self.colors['warning'],
                'justify': tk.CENTER,
                'font': ('Segoe UI', 10, 'italic')
            },
            "timestamp": {
                'foreground': self.colors['text_secondary'],
                'font': ('Segoe UI', 9)
            }
        }

        for tag_name, config in tags_config.items():
            self.messages_text.tag_config(tag_name, **config)

    def create_modern_button(self, parent, text, command):
        """Создание современной кнопки"""
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=self.colors['accent'],
            fg=self.colors['text_primary'],
            font=('Segoe UI', 11),
            relief='flat',
            borderwidth=0,
            padx=20,
            pady=12,
            cursor='hand2',
            anchor='w'
        )

    def create_chat_item(self, parent, text, is_online, is_group=False):
        """Создание элемента списка чатов"""
        chat_frame = tk.Frame(parent, bg=self.colors['secondary'], 
                             relief='flat', borderwidth=0)
        chat_frame.pack(fill=tk.X, padx=5, pady=2)

        # Иконка и статус
        if is_group:
            icon = "👥"
            status_color = self.colors['success'] if is_online else self.colors['text_secondary']
        else:
            icon = "👤"
            status_color = self.colors['success'] if is_online else self.colors['text_secondary']

        icon_label = tk.Label(chat_frame, text=icon, font=('Segoe UI', 12),
                             bg=self.colors['secondary'], fg=self.colors['text_primary'])
        icon_label.pack(side=tk.LEFT, padx=(15, 10))

        # Текст чата
        text_label = tk.Label(chat_frame, text=text, font=('Segoe UI', 11),
                             bg=self.colors['secondary'], fg=self.colors['text_primary'],
                             anchor='w')
        text_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Индикатор статуса
        status_canvas = tk.Canvas(chat_frame, width=8, height=8, bg=self.colors['secondary'],
                                 highlightthickness=0)
        status_canvas.create_oval(0, 0, 8, 8, fill=status_color, outline="")
        status_canvas.pack(side=tk.RIGHT, padx=(0, 15))

        # Привязываем события для hover эффекта
        def on_enter(e):
            chat_frame.configure(bg=self.colors['accent'])
            for child in chat_frame.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=self.colors['accent'])
                elif isinstance(child, tk.Canvas):
                    child.configure(bg=self.colors['accent'])

        def on_leave(e):
            chat_frame.configure(bg=self.colors['secondary'])
            for child in chat_frame.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=self.colors['secondary'])
                elif isinstance(child, tk.Canvas):
                    child.configure(bg=self.colors['secondary'])

        def on_click(e):
            self.on_chat_select(text)

        chat_frame.bind('<Enter>', on_enter)
        chat_frame.bind('<Leave>', on_leave)
        chat_frame.bind('<Button-1>', on_click)

        for child in chat_frame.winfo_children():
            child.bind('<Enter>', on_enter)
            child.bind('<Leave>', on_leave)
            child.bind('<Button-1>', on_click)

        return chat_frame

    def update_char_count(self, event=None):
        """Обновление счетчика символов"""
        text = self.message_entry.get('1.0', 'end-1c')
        count = len(text)
        
        self.char_count_label.config(text=f"{count}/1000")
        
        if count > 900:
            self.char_count_label.config(fg=self.colors['error'])
        elif count > 750:
            self.char_count_label.config(fg=self.colors['warning'])
        else:
            self.char_count_label.config(fg=self.colors['text_secondary'])

    def insert_newline(self, event):
        """Вставка новой строки при Shift+Enter"""
        self.message_entry.insert(tk.INSERT, '\n')
        self.update_char_count()
        return 'break'

    def send_message_enter(self, event):
        """Отправка сообщения по Enter"""
        if event.state == 0:  # Простой Enter
            self.send_message()
            return 'break'
        return None

    def process_queue(self):
        """Обработка очереди сообщений"""
        self.messenger.process_message_queue()
        self.root.after(100, self.process_queue)

    def update_chats_list(self):
        """Обновление списка чатов"""
        # Очищаем текущий список
        for widget in self.chats_frame.winfo_children():
            widget.destroy()

        # Основной групповой чат
        self.create_chat_item(self.chats_frame, "🔥 Основной чат", True, True)

        # Групповые чаты
        for group_id, group_info in self.messenger.groups.items():
            self.create_chat_item(self.chats_frame, f"👥 {group_info['name']}", 
                                group_info['online'], True)

        # Личные чаты
        for contact, info in self.messenger.contacts.items():
            self.create_chat_item(self.chats_frame, f"👤 {contact}", 
                                info['online'], False)

        # Обновляем прокрутку
        self.chats_canvas.configure(scrollregion=self.chats_canvas.bbox('all'))

    def on_chat_select(self, chat_text):
        """Обработка выбора чата"""
        if chat_text.startswith("🔥"):
            self.current_chat = 'MAIN_GROUP'
            self.current_chat_type = 'group'
            self.chat_title.config(text="💬 Основной чат")
        elif chat_text.startswith("👥"):
            group_name = chat_text[2:]
            for group_id, info in self.messenger.groups.items():
                if info['name'] == group_name:
                    self.current_chat = group_id
                    self.current_chat_type = 'group'
                    self.chat_title.config(text=f"👥 {group_name}")
                    break
        elif chat_text.startswith("👤"):
            contact = chat_text[2:]
            self.current_chat = contact
            self.current_chat_type = 'private'
            is_online = self.messenger.contacts[contact]['online']
            status = "🟢" if is_online else "⚫"
            self.chat_title.config(text=f"👤 {contact} {status}")

        self.load_chat_history()

    def load_chat_history(self):
        """Загрузка истории текущего чата"""
        self.messages_text.config(state=tk.NORMAL)
        self.messages_text.delete('1.0', tk.END)

        if self.current_chat_type == 'group':
            if self.current_chat == 'MAIN_GROUP':
                self.messages_text.insert(tk.END, 
                    "Добро пожаловать в основной групповой чат!\n\n", "system")
            else:
                messages = self.messenger.db.get_message_history(
                    self.messenger.username,
                    self.current_chat,
                    'group'
                )
                for sender, text, timestamp in messages:
                    self.display_message(sender, text, timestamp, 'group')
        else:
            messages = self.messenger.db.get_message_history(
                self.messenger.username,
                self.current_chat,
                'private'
            )
            for sender, text, timestamp in messages:
                self.display_message(sender, text, timestamp, 'private')

        self.messages_text.config(state=tk.DISABLED)
        self.messages_text.see(tk.END)

    def display_message(self, sender, text, timestamp, msg_type):
        """Отображение сообщения в чате"""
        self.messages_text.config(state=tk.NORMAL)

        try:
            time_obj = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            time_str = time_obj.strftime('%H:%M')
            date_str = time_obj.strftime('%d.%m.%Y')
        except:
            time_str = timestamp
            date_str = ""

        is_own = sender == self.messenger.username
        tag = "own" if is_own else "other"

        # Форматируем сообщение
        if is_own:
            prefix = f"[{time_str}] Вы\n"
        else:
            prefix = f"[{time_str}] {sender}\n"

        self.messages_text.insert(tk.END, prefix, tag)
        self.messages_text.insert(tk.END, f"{text}\n\n", tag)
        
        self.messages_text.config(state=tk.DISABLED)
        self.messages_text.see(tk.END)

    def handle_group_message(self, message):
        """Обработка входящего группового сообщения"""
        if self.current_chat_type == 'group' and self.current_chat == message['group_id']:
            self.display_message(message['sender'], message['text'], 
                               message['timestamp'], 'group')

    def handle_private_message(self, message):
        """Обработка входящего личного сообщения"""
        if self.current_chat_type == 'private' and self.current_chat == message['sender']:
            self.display_message(message['sender'], message['text'], 
                               message['timestamp'], 'private')

    def send_message(self):
        """Отправка сообщения"""
        text = self.message_entry.get('1.0', 'end-1c').strip()
        if not text:
            return

        if len(text) > 1000:
            self.show_modern_message("Слишком длинное сообщение", 
                                   "Сообщение не должно превышать 1000 символов", "warning")
            return

        # Очищаем поле ввода
        self.message_entry.delete('1.0', tk.END)
        self.update_char_count()

        success = False
        if self.current_chat_type == 'group':
            if self.current_chat == 'MAIN_GROUP':
                success = self.messenger.send_group_message('MAIN_GROUP', text)
            else:
                success = self.messenger.send_group_message(self.current_chat, text)
        else:
            success = self.messenger.send_private_message(self.current_chat, text)

        if success:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.display_message(self.messenger.username, text, timestamp,
                               self.current_chat_type)
        else:
            self.show_modern_message("Ошибка отправки", 
                                   "Не удалось отправить сообщение", "error")

    def add_contact_dialog(self):
        """Современный диалог добавления контакта"""
        self.create_input_dialog("Добавить контакт", "Введите имя пользователя:", 
                               self.messenger.add_contact, "Контакт добавлен")

    def create_group_dialog(self):
        """Современный диалог создания группы"""
        self.create_input_dialog("Создать группу", "Введите название группы:",
                               self.messenger.create_group, "Группа создана")

    def create_input_dialog(self, title, prompt, callback, success_message):
        """Универсальный диалог ввода"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("400x200")
        dialog.configure(bg=self.colors['primary'])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Центрируем диалог
        dialog.geometry(f"+{self.root.winfo_x()+200}+{self.root.winfo_y()+200}")

        # Заголовок
        header = tk.Label(dialog, text=title, font=('Segoe UI', 16, 'bold'),
                         bg=self.colors['primary'], fg=self.colors['text_primary'],
                         pady=20)
        header.pack(fill=tk.X)

        # Поле ввода
        prompt_label = tk.Label(dialog, text=prompt, font=('Segoe UI', 11),
                              bg=self.colors['primary'], fg=self.colors['text_secondary'])
        prompt_label.pack(pady=(0, 10))

        entry_frame = tk.Frame(dialog, bg=self.colors['accent'], relief='flat',
                              borderwidth=0, padx=2, pady=2)
        entry_frame.pack(fill=tk.X, padx=50, pady=10)

        entry = tk.Entry(entry_frame, font=('Segoe UI', 12), bg=self.colors['secondary'],
                        fg=self.colors['text_primary'], relief='flat', borderwidth=0)
        entry.pack(fill=tk.X, padx=10, pady=8)
        entry.focus_set()

        # Кнопки
        button_frame = tk.Frame(dialog, bg=self.colors['primary'])
        button_frame.pack(fill=tk.X, padx=50, pady=20)

        def on_submit():
            value = entry.get().strip()
            if value:
                result = callback(value)
                if result:
                    self.show_modern_message("Успех", success_message, "success")
                    dialog.destroy()
                else:
                    self.show_modern_message("Ошибка", "Операция не выполнена", "error")

        submit_btn = tk.Button(button_frame, text="Подтвердить", command=on_submit,
                              bg=self.colors['highlight'], fg=self.colors['text_primary'],
                              font=('Segoe UI', 11, 'bold'), relief='flat', borderwidth=0,
                              padx=30, pady=10)
        submit_btn.pack(side=tk.RIGHT, padx=(10, 0))

        cancel_btn = tk.Button(button_frame, text="Отмена", command=dialog.destroy,
                              bg=self.colors['accent'], fg=self.colors['text_primary'],
                              font=('Segoe UI', 11), relief='flat', borderwidth=0,
                              padx=30, pady=10)
        cancel_btn.pack(side=tk.RIGHT)

        entry.bind('<Return>', lambda e: on_submit())

    def show_modern_message(self, title, message, msg_type):
        """Показ современного сообщения"""
        color = self.colors.get(msg_type, self.colors['text_primary'])
        
        # Можно реализовать красивый toast вместо messagebox
        messagebox.showinfo(title, message)

    def show_message_history(self):
        """Показ современной истории сообщений"""
        history_window = tk.Toplevel(self.root)
        history_window.title("📜 История сообщений")
        history_window.geometry("1000x800")
        history_window.configure(bg=self.colors['primary'])
        history_window.minsize(900, 600)

        # Заголовок
        header = tk.Label(history_window, text="📜 Полная история сообщений",
                         font=('Segoe UI', 18, 'bold'), bg=self.colors['accent'],
                         fg=self.colors['text_primary'], pady=20)
        header.pack(fill=tk.X)

        # Область истории
        history_text = scrolledtext.ScrolledText(
            history_window,
            wrap=tk.WORD,
            font=('Segoe UI', 10),
            bg=self.colors['secondary'],
            fg=self.colors['text_primary'],
            padx=20,
            pady=20,
            state=tk.NORMAL
        )
        history_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Настройка тегов для истории
        history_text.tag_config("own", foreground=self.colors['highlight'])
        history_text.tag_config("other", foreground=self.colors['text_primary'])
        history_text.tag_config("header", foreground=self.colors['warning'],
                              font=('Segoe UI', 12, 'bold'))

        # Загрузка истории
        messages = self.messenger.get_all_messages(1000)
        history_text.insert(tk.END, "=== ПОЛНАЯ ИСТОРИЯ СООБЩЕНИЙ ===\n\n", "header")

        for sender, receiver, msg_type, text, timestamp in messages:
            msg_type_str = "Группа" if msg_type == 'group' else "Личное"
            time_str = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').strftime('%d.%m %H:%M')

            if sender == self.messenger.username:
                prefix = "📤 Вы ->"
                tag = "own"
            else:
                prefix = f"📥 {sender} ->"
                tag = "other"

            history_text.insert(tk.END,
                              f"[{time_str}] {prefix} {receiver} ({msg_type_str}): {text}\n",
                              tag)

        history_text.config(state=tk.DISABLED)

        # Кнопка закрытия
        close_btn = tk.Button(history_window, text="Закрыть",
                             command=history_window.destroy,
                             bg=self.colors['highlight'],
                             fg=self.colors['text_primary'],
                             font=('Segoe UI', 12, 'bold'),
                             relief='flat', borderwidth=0,
                             padx=40, pady=12)
        close_btn.pack(pady=20)

    def show_profile_menu(self, event=None):
        """Показ меню профиля при клике на ник"""
        menu = tk.Menu(self.root, tearoff=0, bg=self.colors['secondary'], fg=self.colors['text_primary'],
                      activebackground=self.colors['highlight'], activeforeground=self.colors['text_primary'])
        
        menu.add_command(label="✏️ Изменить профиль", command=self.show_profile_settings)
        menu.add_command(label="👤 Сменить имя пользователя", command=self.show_change_username_dialog)
        menu.add_separator()
        menu.add_command(label="🚪 Выйти из аккаунта", command=self.logout)
        
        # Показываем меню рядом с кликом
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def show_profile_settings(self):
        """Показ настроек профиля"""
        profile = self.messenger.get_user_profile()
        
        settings_window = tk.Toplevel(self.root)
        settings_window.title("✏️ Настройки профиля")
        settings_window.geometry("500x400")
        settings_window.configure(bg=self.colors['primary'])
        settings_window.resizable(False, False)
        settings_window.transient(self.root)
        settings_window.grab_set()

        # Центрируем окно
        settings_window.geometry(f"+{self.root.winfo_x()+200}+{self.root.winfo_y()+200}")

        # Заголовок
        header = tk.Label(settings_window, text="✏️ Настройки профиля",
                         font=('Segoe UI', 18, 'bold'), bg=self.colors['accent'],
                         fg=self.colors['text_primary'], pady=20)
        header.pack(fill=tk.X)

        # Основной контейнер
        main_frame = tk.Frame(settings_window, bg=self.colors['primary'], padx=30, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Отображаемое имя
        tk.Label(main_frame, text="Отображаемое имя:", font=('Segoe UI', 11, 'bold'),
                bg=self.colors['primary'], fg=self.colors['text_primary']).pack(anchor='w', pady=(0, 5))
        
        display_name_var = tk.StringVar(value=profile['display_name'] if profile else self.messenger.username)
        display_name_entry = tk.Entry(main_frame, textvariable=display_name_var, font=('Segoe UI', 12),
                                     bg=self.colors['secondary'], fg=self.colors['text_primary'],
                                     relief='flat', borderwidth=0, insertbackground=self.colors['highlight'])
        display_name_entry.pack(fill=tk.X, pady=(0, 15))

        # Статус
        tk.Label(main_frame, text="Статус:", font=('Segoe UI', 11, 'bold'),
                bg=self.colors['primary'], fg=self.colors['text_primary']).pack(anchor='w', pady=(0, 5))
        
        status_var = tk.StringVar(value=profile['status_text'] if profile else 'В сети')
        status_entry = tk.Entry(main_frame, textvariable=status_var, font=('Segoe UI', 12),
                               bg=self.colors['secondary'], fg=self.colors['text_primary'],
                               relief='flat', borderwidth=0, insertbackground=self.colors['highlight'])
        status_entry.pack(fill=tk.X, pady=(0, 20))

        # Информация
        info_frame = tk.Frame(main_frame, bg=self.colors['secondary'], pady=10, padx=15)
        info_frame.pack(fill=tk.X, pady=(0, 20))
        
        tk.Label(info_frame, text="📊 Информация о профиле:", font=('Segoe UI', 11, 'bold'),
                bg=self.colors['secondary'], fg=self.colors['text_primary']).pack(anchor='w')
        
        tk.Label(info_frame, text=f"Имя пользователя: {self.messenger.username}", font=('Segoe UI', 10),
                bg=self.colors['secondary'], fg=self.colors['text_secondary']).pack(anchor='w', pady=(5, 0))
        
        if profile and profile['last_seen']:
            tk.Label(info_frame, text=f"Последний вход: {profile['last_seen']}", font=('Segoe UI', 10),
                    bg=self.colors['secondary'], fg=self.colors['text_secondary']).pack(anchor='w', pady=(2, 0))

        # Кнопки
        button_frame = tk.Frame(main_frame, bg=self.colors['primary'])
        button_frame.pack(fill=tk.X)

        def save_profile():
            display_name = display_name_var.get().strip()
            status_text = status_var.get().strip()
            
            if self.messenger.update_profile(display_name, status_text):
                # Обновляем отображаемое имя в интерфейсе
                self.user_name_label.config(text=f"👤 {display_name}")
                self.show_modern_message("Успех", "Профиль обновлен", "success")
                settings_window.destroy()
            else:
                self.show_modern_message("Ошибка", "Не удалось обновить профиль", "error")

        save_btn = tk.Button(button_frame, text="💾 Сохранить", command=save_profile,
                            bg=self.colors['success'], fg=self.colors['text_primary'],
                            font=('Segoe UI', 12, 'bold'), relief='flat', borderwidth=0,
                            padx=30, pady=12)
        save_btn.pack(side=tk.RIGHT, padx=(10, 0))

        cancel_btn = tk.Button(button_frame, text="Отмена", command=settings_window.destroy,
                              bg=self.colors['accent'], fg=self.colors['text_primary'],
                              font=('Segoe UI', 11), relief='flat', borderwidth=0,
                              padx=30, pady=10)
        cancel_btn.pack(side=tk.RIGHT)

        display_name_entry.focus_set()
        display_name_entry.select_range(0, tk.END)

    def show_change_username_dialog(self):
        """Диалог смены имени пользователя"""
        dialog = tk.Toplevel(self.root)
        dialog.title("👤 Смена имени пользователя")
        dialog.geometry("450x250")
        dialog.configure(bg=self.colors['primary'])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Центрируем диалог
        dialog.geometry(f"+{self.root.winfo_x()+200}+{self.root.winfo_y()+200}")

        # Заголовок
        header = tk.Label(dialog, text="👤 Смена имени пользователя", font=('Segoe UI', 16, 'bold'),
                         bg=self.colors['primary'], fg=self.colors['text_primary'], pady=20)
        header.pack(fill=tk.X)

        # Основной контейнер
        main_frame = tk.Frame(dialog, bg=self.colors['primary'], padx=30)
        main_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        # Текущее имя
        tk.Label(main_frame, text=f"Текущее имя: {self.messenger.username}", font=('Segoe UI', 11),
                bg=self.colors['primary'], fg=self.colors['text_secondary']).pack(anchor='w', pady=(0, 10))

        # Новое имя
        tk.Label(main_frame, text="Новое имя пользователя:", font=('Segoe UI', 11, 'bold'),
                bg=self.colors['primary'], fg=self.colors['text_primary']).pack(anchor='w', pady=(0, 5))

        new_username_var = tk.StringVar()
        username_entry = tk.Entry(main_frame, textvariable=new_username_var, font=('Segoe UI', 12),
                                 bg=self.colors['secondary'], fg=self.colors['text_primary'],
                                 relief='flat', borderwidth=0, insertbackground=self.colors['highlight'])
        username_entry.pack(fill=tk.X, pady=(0, 10))

        # Предупреждение
        warning_label = tk.Label(main_frame, 
                                text="⚠️ После смены имени потребуется перезайти в приложение",
                                font=('Segoe UI', 10), bg=self.colors['primary'], fg=self.colors['warning'])
        warning_label.pack(anchor='w', pady=(0, 15))

        # Кнопки
        button_frame = tk.Frame(main_frame, bg=self.colors['primary'])
        button_frame.pack(fill=tk.X)

        def change_username():
            new_username = new_username_var.get().strip()
            if not new_username:
                self.show_modern_message("Ошибка", "Введите новое имя пользователя", "error")
                return

            if new_username == self.messenger.username:
                self.show_modern_message("Информация", "Имя пользователя не изменилось", "info")
                dialog.destroy()
                return

            success, message = self.messenger.change_username(new_username)
            if success:
                self.show_modern_message("Успех", message, "success")
                dialog.destroy()
                # Перезапускаем приложение
                self.root.after(1000, self.restart_application)
            else:
                self.show_modern_message("Ошибка", message, "error")

        change_btn = tk.Button(button_frame, text="🔄 Сменить", command=change_username,
                              bg=self.colors['highlight'], fg=self.colors['text_primary'],
                              font=('Segoe UI', 11, 'bold'), relief='flat', borderwidth=0,
                              padx=25, pady=10)
        change_btn.pack(side=tk.RIGHT, padx=(10, 0))

        cancel_btn = tk.Button(button_frame, text="Отмена", command=dialog.destroy,
                              bg=self.colors['accent'], fg=self.colors['text_primary'],
                              font=('Segoe UI', 11), relief='flat', borderwidth=0,
                              padx=25, pady=10)
        cancel_btn.pack(side=tk.RIGHT)

        username_entry.focus_set()

    def show_settings_dialog(self):
        """Показ диалога настроек приложения"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("⚙️ Настройки приложения")
        settings_window.geometry("600x700")
        settings_window.configure(bg=self.colors['primary'])
        settings_window.resizable(False, False)
        settings_window.transient(self.root)
        settings_window.grab_set()

        # Центрируем окно
        settings_window.geometry(f"+{self.root.winfo_x()+150}+{self.root.winfo_y()+50}")

        # Заголовок
        header = tk.Label(settings_window, text="⚙️ Настройки приложения",
                         font=('Segoe UI', 18, 'bold'), bg=self.colors['accent'],
                         fg=self.colors['text_primary'], pady=20)
        header.pack(fill=tk.X)

        # Основной контейнер с прокруткой
        canvas = tk.Canvas(settings_window, bg=self.colors['primary'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(settings_window, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors['primary'])

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Настройки
        self.create_settings_section(scrollable_frame, "🔔 Уведомления", [
            ("Показывать уведомления", "notifications", "bool"),
            ("Звуковые эффекты", "sound_effects", "bool")
        ])

        self.create_settings_section(scrollable_frame, "💬 Сообщения", [
            ("Лимит истории сообщений", "message_history_limit", "int"),
            ("Размер шрифта", "font_size", "int")
        ])

        self.create_settings_section(scrollable_frame, "🚀 Запуск", [
            ("Автоматический вход", "auto_login", "bool"),
            ("Запуск свернутым", "start_minimized", "bool")
        ])

        self.create_settings_section(scrollable_frame, "👤 Профиль", [
            ("Показывать статус онлайн", "show_online_status", "bool")
        ])

        # Кнопки
        button_frame = tk.Frame(settings_window, bg=self.colors['primary'], pady=20)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM)

        save_btn = tk.Button(button_frame, text="💾 Сохранить настройки",
                           command=lambda: self.save_settings(settings_window),
                           bg=self.colors['success'], fg=self.colors['text_primary'],
                           font=('Segoe UI', 12, 'bold'), relief='flat', borderwidth=0,
                           padx=30, pady=12)
        save_btn.pack(side=tk.RIGHT, padx=20)

        cancel_btn = tk.Button(button_frame, text="Отмена", command=settings_window.destroy,
                              bg=self.colors['accent'], fg=self.colors['text_primary'],
                              font=('Segoe UI', 11), relief='flat', borderwidth=0,
                              padx=25, pady=10)
        cancel_btn.pack(side=tk.RIGHT)

        # Упаковываем canvas и scrollbar
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=20, pady=20)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def create_settings_section(self, parent, title, settings):
        """Создание секции настроек"""
        section_frame = tk.Frame(parent, bg=self.colors['secondary'], pady=15, padx=20)
        section_frame.pack(fill=tk.X, padx=20, pady=10)

        # Заголовок секции
        tk.Label(section_frame, text=title, font=('Segoe UI', 14, 'bold'),
                bg=self.colors['secondary'], fg=self.colors['text_primary']).pack(anchor='w', pady=(0, 10))

        # Настройки
        for setting_name, setting_key, setting_type in settings:
            setting_frame = tk.Frame(section_frame, bg=self.colors['secondary'])
            setting_frame.pack(fill=tk.X, pady=5)

            tk.Label(setting_frame, text=setting_name, font=('Segoe UI', 11),
                    bg=self.colors['secondary'], fg=self.colors['text_primary']).pack(side=tk.LEFT)

            if setting_type == "bool":
                var = tk.BooleanVar(value=self.messenger.settings.get(setting_key, True))
                checkbox = tk.Checkbutton(setting_frame, variable=var, 
                                        bg=self.colors['secondary'], fg=self.colors['text_primary'],
                                        selectcolor=self.colors['highlight'],
                                        activebackground=self.colors['secondary'],
                                        activeforeground=self.colors['text_primary'])
                checkbox.var = var
                checkbox.setting_key = setting_key
                checkbox.pack(side=tk.RIGHT)
            elif setting_type == "int":
                var = tk.StringVar(value=str(self.messenger.settings.get(setting_key, 1000)))
                entry = tk.Entry(setting_frame, textvariable=var, width=8,
                                bg=self.colors['primary'], fg=self.colors['text_primary'],
                                relief='flat', borderwidth=1)
                entry.var = var
                entry.setting_key = setting_key
                entry.pack(side=tk.RIGHT)

    def save_settings(self, settings_window):
        """Сохранение настроек"""
        # Собираем все настройки из виджетов
        for widget in settings_window.winfo_children():
            if isinstance(widget, tk.Canvas):
                for child in widget.winfo_children():
                    if isinstance(child, tk.Frame):
                        self.process_settings_frame(child)
        
        self.messenger.settings.save_settings()
        self.show_modern_message("Успех", "Настройки сохранены", "success")
        settings_window.destroy()

    def process_settings_frame(self, frame):
        """Обработка фрейма с настройками"""
        for child in frame.winfo_children():
            if hasattr(child, 'var') and hasattr(child, 'setting_key'):
                value = child.var.get()
                if isinstance(child, tk.Checkbutton):
                    self.messenger.settings.set(child.setting_key, value)
                elif isinstance(child, tk.Entry):
                    try:
                        if child.setting_key == 'font_size':
                            self.messenger.settings.set(child.setting_key, int(value))
                        else:
                            self.messenger.settings.set(child.setting_key, int(value))
                    except ValueError:
                        pass

            # Рекурсивно обрабатываем вложенные фреймы
            if isinstance(child, tk.Frame):
                self.process_settings_frame(child)

    def logout(self):
        """Выход из аккаунта"""
        if messagebox.askyesno("Выход", "Вы уверены, что хотите выйти из аккаунта?"):
            self.messenger.stop()
            self.root.destroy()
            # Перезапускаем приложение для показа окна входа
            main()

    def restart_application(self):
        """Перезапуск приложения"""
        self.messenger.stop()
        self.root.destroy()
        main()


class ModernLoginWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("✨ NeoChat - Вход в систему")
        self.root.geometry("500x650")
        self.root.configure(bg='#1a1a2e')
        self.root.resizable(False, False)
        
        # Менеджер пользователей
        self.user_manager = UserManager()
        self.auto_login_attempted = False
        
        # Центрируем окно
        self.center_window()
        
        self.db = DatabaseManager()
        self.setup_ui()
        
        # Проверяем запомненных пользователей и предлагаем авторизацию
        self.check_remembered_users()

    def center_window(self):
        """Центрирование окна на экране"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def get_local_ip(self):
        """Получение локального IP адреса"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except:
            return "unknown"

    def check_remembered_users(self):
        """Проверка запомненных пользователей и автоматическая авторизация"""
        local_ip = self.get_local_ip()
        remembered_user = self.user_manager.get_remembered_user(local_ip)
        
        if remembered_user and remembered_user.get('auto_login'):
            username = remembered_user['username']
            password_hash = remembered_user.get('password_hash')
            
            if password_hash and self.db.authenticate_with_hash(username, password_hash):
                self.auto_login_attempted = True
                self.show_auto_login_notification(username)
                self.root.after(1000, lambda: self.auto_login(username))
            else:
                self.show_auth_button(remembered_user)
        elif remembered_user:
            self.show_auth_button(remembered_user)

    def show_auto_login_notification(self, username):
        """Показ уведомления об автоматической авторизации"""
        notification_frame = tk.Frame(self.main_container, bg='#00b894', relief='flat', borderwidth=0)
        notification_frame.pack(fill=tk.X, pady=(0, 10), padx=20)
        
        notification_label = tk.Label(notification_frame, 
                                    text=f"🔄 Автоматическая авторизация для {username}...",
                                    font=('Segoe UI', 11, 'bold'),
                                    bg='#00b894', fg='#ffffff',
                                    pady=10)
        notification_label.pack()

    def auto_login(self, username):
        """Автоматический вход без пароля"""
        self.start_messenger(username)

    def show_auth_button(self, remembered_user):
        """Показ кнопки авторизации для запомненного пользователя"""
        username = remembered_user['username']
        
        auth_frame = tk.Frame(self.main_container, bg='#1a1a2e', pady=10)
        auth_frame.pack(fill=tk.X, before=self.form_frame)
        
        auth_label = tk.Label(auth_frame, 
                             text=f"🕐 Найден сохраненный пользователь: {username}",
                             font=('Segoe UI', 11),
                             bg='#1a1a2e', fg='#00b894')
        auth_label.pack(pady=(0, 10))
        
        auth_btn = tk.Button(auth_frame, 
                            text=f"🔓 Авторизоваться как {username}",
                            command=lambda: self.auth_without_password(username),
                            bg='#00b894', fg='#ffffff',
                            font=('Segoe UI', 12, 'bold'),
                            relief='flat', borderwidth=0,
                            padx=20, pady=12,
                            cursor='hand2')
        auth_btn.pack(fill=tk.X, pady=(0, 5))
        
        different_btn = tk.Button(auth_frame,
                                 text="👤 Войти под другим пользователем",
                                 command=self.clear_auth_section,
                                 bg='#fdcb6e', fg='#2d3436',
                                 font=('Segoe UI', 10),
                                 relief='flat', borderwidth=0,
                                 padx=20, pady=8,
                                 cursor='hand2')
        different_btn.pack(fill=tk.X)

    def auth_without_password(self, username):
        """Авторизация без пароля для запомненного пользователя"""
        local_ip = self.get_local_ip()
        remembered_user = self.user_manager.get_remembered_user(local_ip)
        
        if remembered_user and remembered_user['username'] == username:
            password_hash = remembered_user.get('password_hash')
            if password_hash and self.db.authenticate_with_hash(username, password_hash):
                self.start_messenger(username)
            else:
                self.quick_login(username)
        else:
            self.quick_login(username)

    def clear_auth_section(self):
        """Очистка секции авторизации"""
        for widget in self.main_container.winfo_children():
            if hasattr(widget, 'auth_section') and widget.auth_section:
                widget.destroy()

    def quick_login(self, username):
        """Быстрый вход для запомненного пользователя с запросом пароля"""
        password = simpledialog.askstring("Быстрый вход", 
                                         f"Введите пароль для {username}:", 
                                         show='*')
        if password:
            success, password_hash = self.db.authenticate_user(username, password)
            if success:
                local_ip = self.get_local_ip()
                self.user_manager.remember_user(local_ip, username, password_hash)
                self.start_messenger(username)
            else:
                messagebox.showerror("Ошибка", "Неверный пароль")

    def forget_user(self):
        """Забыть пользователя"""
        local_ip = self.get_local_ip()
        remembered_user = self.user_manager.get_remembered_user(local_ip)
        if remembered_user:
            username = remembered_user['username']
            self.user_manager.forget_user(local_ip)
            messagebox.showinfo("Успех", f"Пользователь {username} забыт")
            self.root.destroy()
            main()

    def remember_current_user(self):
        """Запомнить текущего пользователя"""
        local_ip = self.get_local_ip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        
        if username and username != "Имя пользователя" and password and password != "Пароль":
            success, password_hash = self.db.authenticate_user(username, password)
            if success:
                self.user_manager.remember_user(local_ip, username, password_hash)

    def setup_ui(self):
        """Настройка современного интерфейса входа"""
        self.main_container = tk.Frame(self.root, bg='#1a1a2e')
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)

        logo_frame = tk.Frame(self.main_container, bg='#1a1a2e', pady=20)
        logo_frame.pack(fill=tk.X)

        logo = tk.Label(logo_frame, text="✨", font=('Segoe UI', 48),
                       bg='#1a1a2e', fg='#e94560')
        logo.pack()

        title = tk.Label(logo_frame, text="NeoChat", font=('Segoe UI', 32, 'bold'),
                        bg='#1a1a2e', fg='#ffffff')
        title.pack(pady=(10, 5))

        subtitle = tk.Label(logo_frame, text="Современный мессенджер",
                           font=('Segoe UI', 14), bg='#1a1a2e', fg='#b8b8b8')
        subtitle.pack()

        self.form_frame = tk.Frame(self.main_container, bg='#1a1a2e', pady=20)
        self.form_frame.pack(fill=tk.X)

        username_frame = tk.Frame(self.form_frame, bg='#16213e', relief='flat',
                                 borderwidth=0, padx=2, pady=2)
        username_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(username_frame, text="👤", font=('Segoe UI', 14),
                bg='#16213e', fg='#e94560').pack(side=tk.LEFT, padx=(15, 10))

        self.username_entry = tk.Entry(username_frame, font=('Segoe UI', 14),
                                      bg='#0f3460', fg='#ffffff',
                                      insertbackground='#e94560',
                                      relief='flat', borderwidth=0)
        self.username_entry.pack(fill=tk.X, padx=(0, 15), pady=12)
        self.username_entry.insert(0, "Имя пользователя")
        self.username_entry.bind('<FocusIn>', self.clear_placeholder)
        self.username_entry.bind('<FocusOut>', self.restore_placeholder)

        password_frame = tk.Frame(self.form_frame, bg='#16213e', relief='flat',
                                 borderwidth=0, padx=2, pady=2)
        password_frame.pack(fill=tk.X, pady=(0, 20))

        tk.Label(password_frame, text="🔒", font=('Segoe UI', 14),
                bg='#16213e', fg='#e94560').pack(side=tk.LEFT, padx=(15, 10))

        self.password_entry = tk.Entry(password_frame, font=('Segoe UI', 14),
                                      show='', bg='#0f3460', fg='#666666',
                                      insertbackground='#e94560',
                                      relief='flat', borderwidth=0)
        self.password_entry.pack(fill=tk.X, padx=(0, 15), pady=12)
        self.password_entry.insert(0, "Пароль")
        self.password_entry.bind('<FocusIn>', self.clear_placeholder_password)
        self.password_entry.bind('<FocusOut>', self.restore_placeholder_password)

        self.remember_var = tk.BooleanVar(value=True)
        remember_frame = tk.Frame(self.form_frame, bg='#1a1a2e')
        remember_frame.pack(fill=tk.X, pady=(0, 20))

        remember_cb = tk.Checkbutton(remember_frame, 
                                    text="Запомнить меня на этом устройстве",
                                    variable=self.remember_var,
                                    bg='#1a1a2e', fg='#b8b8b8',
                                    selectcolor='#0f3460',
                                    font=('Segoe UI', 11),
                                    activebackground='#1a1a2e',
                                    activeforeground='#b8b8b8')
        remember_cb.pack(anchor='w')

        button_frame = tk.Frame(self.main_container, bg='#1a1a2e')
        button_frame.pack(fill=tk.X, pady=15)

        auth_btn = tk.Button(button_frame, text="🔓 Авторизоваться",
                           command=self.login,
                           bg='#e94560', fg='#ffffff',
                           font=('Segoe UI', 14, 'bold'),
                           relief='flat', borderwidth=0,
                           padx=30, pady=15,
                           cursor='hand2')
        auth_btn.pack(fill=tk.X, pady=(0, 10))

        secondary_btn_frame = tk.Frame(button_frame, bg='#1a1a2e')
        secondary_btn_frame.pack(fill=tk.X)

        register_btn = tk.Button(secondary_btn_frame, text="Создать аккаунт",
                                command=self.register,
                                bg='#16213e', fg='#ffffff',
                                font=('Segoe UI', 12),
                                relief='flat', borderwidth=0,
                                padx=20, pady=10,
                                cursor='hand2')
        register_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.forget_btn = tk.Button(secondary_btn_frame, text="Забыть пользователя",
                                   command=self.forget_user,
                                   bg='#d63031', fg='#ffffff',
                                   font=('Segoe UI', 10),
                                   relief='flat', borderwidth=0,
                                   padx=15, pady=8,
                                   cursor='hand2')
        self.forget_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        local_ip = self.get_local_ip()
        remembered_user = self.user_manager.get_remembered_user(local_ip)
        if not remembered_user:
            self.forget_btn.pack_forget()

        ip_frame = tk.Frame(self.main_container, bg='#1a1a2e', pady=10)
        ip_frame.pack(fill=tk.X)
        
        ip_info = tk.Label(ip_frame, 
                          text=f"🌐 Ваш IP: {self.get_local_ip()}",
                          font=('Segoe UI', 10),
                          bg='#1a1a2e', fg='#b8b8b8')
        ip_info.pack()

        self.username_entry.bind('<Return>', lambda e: self.password_entry.focus_set())
        self.password_entry.bind('<Return>', lambda e: self.login())

        self.username_entry.focus_set()

    def clear_placeholder(self, event):
        if self.username_entry.get() == "Имя пользователя":
            self.username_entry.delete(0, tk.END)
            self.username_entry.config(fg='#ffffff')

    def restore_placeholder(self, event):
        if not self.username_entry.get():
            self.username_entry.insert(0, "Имя пользователя")
            self.username_entry.config(fg='#666666')

    def clear_placeholder_password(self, event):
        if self.password_entry.get() == "Пароль":
            self.password_entry.delete(0, tk.END)
            self.password_entry.config(show='•', fg='#ffffff')

    def restore_placeholder_password(self, event):
        if not self.password_entry.get():
            self.password_entry.config(show='')
            self.password_entry.insert(0, "Пароль")
            self.password_entry.config(fg='#666666')

    def login(self):
        if self.auto_login_attempted:
            return
            
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if username == "Имя пользователя" or not username:
            self.show_error("Введите имя пользователя")
            return

        if password == "Пароль" or not password:
            self.show_error("Введите пароль")
            return

        success, password_hash = self.db.authenticate_user(username, password)
        if success:
            if self.remember_var.get():
                self.remember_current_user()
            self.start_messenger(username)
        else:
            self.show_error("Неверное имя пользователя или пароль")

    def register(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if username == "Имя пользователя" or not username:
            self.show_error("Введите имя пользователя")
            return

        if password == "Пароль" or not password:
            self.show_error("Введите пароль")
            return

        if len(username) < 3:
            self.show_error("Имя пользователя должно содержать минимум 3 символа")
            return

        if len(password) < 4:
            self.show_error("Пароль должен содержать минимум 4 символа")
            return

        success, password_hash = self.db.register_user(username, password)
        if success:
            if self.remember_var.get():
                local_ip = self.get_local_ip()
                self.user_manager.remember_user(local_ip, username, password_hash)
            self.show_success("Регистрация завершена. Теперь вы можете войти.")
            self.start_messenger(username)
        else:
            self.show_error("Пользователь с таким именем уже существует")

    def show_error(self, message):
        messagebox.showerror("Ошибка", message)

    def show_success(self, message):
        messagebox.showinfo("Успех", message)

    def start_messenger(self, username):
        self.root.withdraw()

        main_root = tk.Toplevel(self.root)
        messenger = MulticastMessenger(username)
        messenger.start()

        gui = ModernMessengerGUI(main_root, messenger)

        def on_closing():
            if messagebox.askokcancel("Выход", "Вы уверены, что хотите выйти?"):
                messenger.stop()
                main_root.destroy()
                self.root.destroy()

        main_root.protocol("WM_DELETE_WINDOW", on_closing)
        main_root.focus_set()


def main():
    root = tk.Tk()
    login_app = ModernLoginWindow(root)

    def on_closing():
        if messagebox.askokcancel("Выход", "Вы уверены, что хотите выйти?"):
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
