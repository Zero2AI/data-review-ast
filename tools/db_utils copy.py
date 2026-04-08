import os
import sqlite3
import pandas as pd
import streamlit as st
from typing import Optional, Union, List, Dict, Any
from contextlib import contextmanager

class DatabaseConnection:
    """
    A class to manage database connections using DB-API 2.0.
    """
    def __init__(self, db_path: str = None, study_name: str = None):
        """Initialize database connection manager."""
        if study_name:
            self.db_path = DatabaseConnection.get_study_db_path(study_name)
            self.study_name = study_name
        else:
            self.db_path = db_path
            self.study_name = None
        
        if self.db_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        
        # Create protocols directory for the study
        if study_name:
            self.protocols_dir = os.path.join(os.getcwd(), "studies", study_name, "protocols")
        else:
            self.protocols_dir = os.path.join(os.getcwd(), "protocols")
        os.makedirs(self.protocols_dir, exist_ok=True)
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.
        Ensures proper handling of connections and cursors.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()
    def execute_query(self, query: str, params: Optional[tuple] = None) -> pd.DataFrame:
        """
        Execute a SQL query and return results as a DataFrame.
        """
        with self.get_connection() as conn:
            try:
                if params:
                    return pd.read_sql_query(query, conn, params=params)
                df = pd.read_sql_query(query, conn)
                return df
            except Exception as e:
                raise Exception(f"Query execution failed: {str(e)}")
    
    def execute_write_query(self, query: str, params: Optional[Union[tuple, List[tuple]]] = None) -> None:
        """
        Execute a write query (INSERT, UPDATE, DELETE).
        """
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor()
                if params:
                    if isinstance(params, list):
                        cursor.executemany(query, params)
                    else:
                        cursor.execute(query, params)
                else:
                    cursor.execute(query)
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise Exception(f"Write operation failed: {str(e)}")
    
    def save_dataframe(self, df: pd.DataFrame, table_name: str) -> None:
        """
        Save a pandas DataFrame to the database.
        
        Args:
            df: DataFrame to save
            table_name: Name of the table
        """
        with self.get_connection() as conn:
            try:
               
                safe_table_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in table_name)
                
               
                df.columns = [f"{c}".replace(" ", "_").replace("-", "_") for c in df.columns]
                
               
                if not safe_table_name or safe_table_name[0].isdigit():
                    safe_table_name = f"table_{safe_table_name}"
                
                # Save DataFrame to SQL table
                df.to_sql(safe_table_name, conn, if_exists='replace', index=False)
                
                # Commit the transaction to persist changes
                conn.commit()
                
                # Verify table creation
                cursor = conn.cursor()
                cursor.execute(f'PRAGMA table_info("{safe_table_name}")')
                if not cursor.fetchall():
                    raise Exception("Table creation failed")
                
               
                
            except Exception as e:
                raise Exception(f"Failed to save DataFrame: {str(e)}")
    
    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get schema information for a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of column information dictionaries
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
               
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                    (table_name,)
                )
                if not cursor.fetchone():
                    return []
                
               
                safe_table_name = table_name.replace('"', '""')
                cursor.execute(f'PRAGMA table_info("{safe_table_name}")')
                columns = cursor.fetchall()
                
                if not columns:
                    return []
                    
                return [
                    {
                        'name': col[1],
                        'type': col[2],
                        'notnull': bool(col[3]),
                        'pk': bool(col[5])
                    }
                    for col in columns
                ]
            except Exception as e:
                st.error(f"Error reading schema for table '{table_name}': {str(e)}")
                return []
    
    @staticmethod
    @staticmethod
    def get_study_db_path(study_name: str) -> str:
        """Get database path for specific study"""
        return os.path.join(os.getcwd(), "studies", study_name, "data", "app.db")
    
    @staticmethod
    def create_study_directories(study_name: str) -> bool:
        """Create directory structure for new study"""
        try:
            study_base = os.path.join(os.getcwd(), "studies", study_name)
            data_dir = os.path.join(study_base, "data")
            protocols_dir = os.path.join(study_base, "protocols")
            
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(protocols_dir, exist_ok=True)
            return True
        except Exception as e:
            print(f"Error creating study directories: {str(e)}")
            return False
    
    @staticmethod
    def create_study(study_name: str, description: str = "") -> bool:
        """Create a new study with directories and database"""
        try:
            # Create directory structure
            if not DatabaseConnection.create_study_directories(study_name):
                return False
            
            # Create database connection for the new study
            db_path = DatabaseConnection.get_study_db_path(study_name)
            
            # Initialize the database (this will create the file)
            conn = sqlite3.connect(db_path)
            try:
                # Database file is created by sqlite3.connect()
                # No need to create any tables here - they will be created when data is uploaded
                conn.commit()
                return True
                
            except Exception as e:
                print(f"Error initializing study database: {str(e)}")
                return False
            finally:
                conn.close()
                
        except Exception as e:
            print(f"Error creating study: {str(e)}")
            return False
    
    @staticmethod
    def list_available_studies() -> List[str]:
        """Get list of available studies"""
        studies_dir = os.path.join(os.getcwd(), "studies")
        if not os.path.exists(studies_dir):
            return []
        
        studies = []
        try:
            for item in os.listdir(studies_dir):
                item_path = os.path.join(studies_dir, item)
                if os.path.isdir(item_path):
                    # Check if it has the required structure
                    data_dir = os.path.join(item_path, "data")
                    if os.path.exists(data_dir):
                        studies.append(item)
            return sorted(studies)
        except Exception as e:
            print(f"Error listing studies: {str(e)}")
            return []
    
    @staticmethod
    def validate_study_name(study_name: str) -> bool:
        """Validate study name for safety"""
        if not study_name or not isinstance(study_name, str):
            return False
        
        # Check for valid characters (alphanumeric, underscore, hyphen, space)
        import re
        if not re.match(r'^[a-zA-Z0-9_\-\s]+$', study_name):
            return False
        
        # Check length
        if len(study_name) < 1 or len(study_name) > 100:
            return False
        
        # Check for reserved names
        reserved_names = ['con', 'prn', 'aux', 'nul', 'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9', 'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9']
        if study_name.lower() in reserved_names:
            return False
        
        return True
    
    @staticmethod
    def database_exists(study_name: str) -> bool:
        """Check if database file exists for a study"""
        try:
            db_path = DatabaseConnection.get_study_db_path(study_name)
            return os.path.exists(db_path) and os.path.getsize(db_path) > 0
        except Exception:
            return False
    
    @staticmethod
    def get_safe_table_count(study_name: str) -> tuple[int, str, bool]:
        """
        Safely get table count for a study
        Returns: (table_count, status_message, has_error)
        """
        try:
            # Get the database path first
            db_path = DatabaseConnection.get_study_db_path(study_name)
            
            # Check if database file actually exists before creating connection
            if not os.path.exists(db_path):
                return (0, "no database", False)
            
            # Check if file has content (not empty)
            if os.path.getsize(db_path) == 0:
                return (0, "empty database", False)
            
            # Only create connection if database file exists and has content
            study_db = DatabaseConnection(study_name=study_name)
            tables = study_db.list_tables()
            return (len(tables), "active", False)
            
        except sqlite3.DatabaseError as e:
            return (0, "corrupted", True)
        except PermissionError:
            return (0, "permission denied", True)
        except Exception as e:
            return (0, f"error: {str(e)[:20]}...", True)
    
    @staticmethod
    def check_protocol_files(study_name: str) -> Dict[str, bool]:
        """Check which protocol files exist for a study"""
        try:
            protocols_dir = os.path.join(os.getcwd(), "studies", study_name, "protocols")
            protocol_files = {
                'protocol.pdf': False,
                'annotation.pdf': False,
                'QUESTIONS.csv': False
            }
            
            if os.path.exists(protocols_dir):
                for file_name in protocol_files.keys():
                    file_path = os.path.join(protocols_dir, file_name)
                    protocol_files[file_name] = os.path.exists(file_path) and os.path.getsize(file_path) > 0
            
            return protocol_files
        except Exception:
            return {'protocol.pdf': False, 'annotation.pdf': False, 'QUESTIONS.csv': False}
    
    @staticmethod
    def get_study_metadata(study_name: str) -> Dict[str, Any]:
        """Get comprehensive metadata for a study"""
        try:
            metadata = {
                'name': study_name,
                'exists': True,
                'table_count': 0,
                'status': 'unknown',
                'has_error': False,
                'protocols': {'protocol.pdf': False, 'annotation.pdf': False, 'QUESTIONS.csv': False},
                'database_size': 0,
                'created_date': None
            }
            
            # Get table information
            table_count, status, has_error = DatabaseConnection.get_safe_table_count(study_name)
            metadata['table_count'] = table_count
            metadata['status'] = status
            metadata['has_error'] = has_error
            
            # Get protocol information
            metadata['protocols'] = DatabaseConnection.check_protocol_files(study_name)
            
            # Get database file size if it exists
            if DatabaseConnection.database_exists(study_name):
                try:
                    db_path = DatabaseConnection.get_study_db_path(study_name)
                    metadata['database_size'] = os.path.getsize(db_path)
                    metadata['created_date'] = os.path.getctime(db_path)
                except Exception:
                    pass
            
            return metadata
            
        except Exception as e:
            return {
                'name': study_name,
                'exists': False,
                'table_count': 0,
                'status': f'error: {str(e)[:20]}...',
                'has_error': True,
                'protocols': {'protocol.pdf': False, 'annotation.pdf': False, 'QUESTIONS.csv': False},
                'database_size': 0,
                'created_date': None
            }
    
    @staticmethod
    def migrate_legacy_database() -> bool:
        """Migrate existing app.db to study structure"""
        try:
            old_db_path = os.path.join(os.getcwd(), "data", "app.db")
            old_protocols_dir = os.path.join(os.getcwd(), "protocols")
            
            # Check if legacy structure exists
            if not os.path.exists(old_db_path):
                return False  # No migration needed
            
            # Create default study structure
            default_study = "default"
            if not DatabaseConnection.create_study_directories(default_study):
                return False
            
            new_db_path = DatabaseConnection.get_study_db_path(default_study)
            new_protocols_dir = os.path.join(os.getcwd(), "studies", default_study, "protocols")
            
            # Copy database file
            import shutil
            shutil.copy2(old_db_path, new_db_path)
            
            # Copy protocol files if they exist
            if os.path.exists(old_protocols_dir):
                for file_name in os.listdir(old_protocols_dir):
                    old_file = os.path.join(old_protocols_dir, file_name)
                    new_file = os.path.join(new_protocols_dir, file_name)
                    if os.path.isfile(old_file):
                        shutil.copy2(old_file, new_file)
            
            # Rename old directories to avoid conflicts
            if os.path.exists(old_db_path):
                backup_data_dir = os.path.join(os.getcwd(), "data_backup")
                if os.path.exists(os.path.join(os.getcwd(), "data")):
                    shutil.move(os.path.join(os.getcwd(), "data"), backup_data_dir)
            
            if os.path.exists(old_protocols_dir):
                backup_protocols_dir = os.path.join(os.getcwd(), "protocols_backup")
                shutil.move(old_protocols_dir, backup_protocols_dir)
            
            return True
        except Exception as e:
            print(f"Error during migration: {str(e)}")
            return False
    
    @staticmethod
    def delete_study(study_name: str) -> bool:
        """
        Delete entire study directory and all its contents
        
        Args:
            study_name: Name of the study to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            import shutil
            import time
            import gc
            
            # Validate study name
            if not DatabaseConnection.validate_study_name(study_name):
                print(f"Invalid study name: {study_name}")
                return False
            
            # Get study directory path
            study_dir = os.path.join(os.getcwd(), "studies", study_name)
            
            # Check if study directory exists
            if not os.path.exists(study_dir):
                print(f"Study directory does not exist: {study_dir}")
                return False  # Study doesn't exist
            
            # Force close any open database connections to this study
            try:
                db_path = DatabaseConnection.get_study_db_path(study_name)
                if os.path.exists(db_path):
                    # Force garbage collection to release any open connections
                    gc.collect()
                    time.sleep(0.2)  # Give time for handles to release
                    
                    # Try to remove the database file first
                    try:
                        os.remove(db_path)
                        print(f"Successfully removed database file: {db_path}")
                    except PermissionError as pe:
                        print(f"Permission error removing database: {pe}")
                        # Try a more aggressive approach for Windows
                        time.sleep(0.5)
                        gc.collect()
                        try:
                            os.remove(db_path)
                            print(f"Successfully removed database on retry: {db_path}")
                        except Exception as e2:
                            print(f"Failed to remove database after retry: {e2}")
                            # Continue anyway, try to delete the whole directory
                    except Exception as e:
                        print(f"Error removing database file: {e}")
                        # Continue anyway
            except Exception as e:
                print(f"Error in database cleanup: {e}")
                # Continue anyway
            
            # Force another garbage collection before directory removal
            gc.collect()
            time.sleep(0.1)
            
            # Remove the entire study directory
            try:
                shutil.rmtree(study_dir)
                print(f"Successfully removed study directory: {study_dir}")
                return True
            except PermissionError as pe:
                print(f"Permission error removing directory: {pe}")
                # Try one more time with a longer delay
                time.sleep(1.0)
                gc.collect()
                try:
                    shutil.rmtree(study_dir)
                    print(f"Successfully removed directory on retry: {study_dir}")
                    return True
                except Exception as e2:
                    print(f"Failed to remove directory after retry: {e2}")
                    return False
            except Exception as e:
                print(f"Error removing directory: {e}")
                return False
            
        except PermissionError as e:
            print(f"Permission error deleting study '{study_name}': {str(e)}")
            return False
        except Exception as e:
            print(f"Error deleting study '{study_name}': {str(e)}")
            return False
    
    @staticmethod
    def get_study_deletion_info(study_name: str) -> Dict[str, Any]:
        """
        Get information about what will be deleted for a study
        
        Args:
            study_name: Name of the study
            
        Returns:
            Dict containing deletion information
        """
        try:
            info = {
                'study_name': study_name,
                'exists': False,
                'total_size': 0,
                'database_size': 0,
                'protocol_files': [],
                'table_count': 0,
                'total_files': 0
            }
            
            study_dir = os.path.join(os.getcwd(), "studies", study_name)
            
            if not os.path.exists(study_dir):
                return info
            
            info['exists'] = True
            
            # Calculate total directory size and count files
            total_size = 0
            total_files = 0
            
            for root, dirs, files in os.walk(study_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        total_size += file_size
                        total_files += 1
                        
                        # Track specific files
                        if file == 'app.db':
                            info['database_size'] = file_size
                        elif file in ['protocol.pdf', 'annotation.pdf', 'QUESTIONS.csv']:
                            info['protocol_files'].append({
                                'name': file,
                                'size': file_size
                            })
                    except OSError:
                        continue
            
            info['total_size'] = total_size
            info['total_files'] = total_files
            
            # Get table count if database exists
            if DatabaseConnection.database_exists(study_name):
                table_count, _, _ = DatabaseConnection.get_safe_table_count(study_name)
                info['table_count'] = table_count
            
            return info
            
        except Exception as e:
            print(f"Error getting deletion info for study '{study_name}': {str(e)}")
            return {
                'study_name': study_name,
                'exists': False,
                'total_size': 0,
                'database_size': 0,
                'protocol_files': [],
                'table_count': 0,
                'total_files': 0,
                'error': str(e)
            }
    
    def switch_to_study(self, study_name: str) -> bool:
        """Switch database connection to different study"""
        try:
            new_db_path = self.get_study_db_path(study_name)
            if os.path.exists(new_db_path):
                self.db_path = new_db_path
                self.study_name = study_name
                self.protocols_dir = os.path.join(os.getcwd(), "studies", study_name, "protocols")
                return True
            return False
        except Exception as e:
            print(f"Error switching to study: {str(e)}")
            return False
    
    def list_tables(self) -> List[str]:
        """
        Get a list of user data tables in the database (excludes system tables).
        
        Returns:
            List of user table names
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                all_tables = [table[0] for table in cursor.fetchall()]
                # Filter out system tables to show only user data tables
                system_tables = ['sqlite_sequence']
                return [table for table in all_tables if table not in system_tables]
            except Exception as e:
                raise Exception(f"Failed to list tables: {str(e)}")
    
    def execute_multi_query(self, queries: List[str]) -> Dict[str, pd.DataFrame]:
        """
        Execute multiple SQL queries and return results as a dictionary of DataFrames.
        
        Args:
            queries (List[str]): List of SQL queries to execute
            
        Returns:
            Dict[str, pd.DataFrame]: Dictionary mapping query index to result DataFrame
        """
        from tools.llm_tools import execute_multi_query
        
        with self.get_connection() as conn:
            try:
                return execute_multi_query(conn, queries)
            except Exception as e:
                raise Exception(f"Multi-query execution failed: {str(e)}")
    
    def execute_single_query(self, query: str) -> pd.DataFrame:
        """
        Execute a single SQL query and return results as a DataFrame.
        This is a wrapper around execute_query for consistency with single-query mode.
        """
        return self.execute_query(query)
    
    def get_distinct_values(self, table_name: str, column_name: str) -> List[str]:
        """Get all distinct values from a specific column."""
        query = f'SELECT DISTINCT "{column_name}" FROM "{table_name}" WHERE "{column_name}" IS NOT NULL'
        with self.get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute(query)
                values = cursor.fetchall()
                return [value[0] for value in values if value[0]]
            except Exception as e:
                print(f"Error getting distinct values: {str(e)}")
                return []

# Global db instance will be created dynamically in app.py based on selected study