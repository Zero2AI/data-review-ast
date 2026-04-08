import pandas as pd
import numpy as np

class SearchPatients:
    """Tool to search for patients based on filters"""
    
    def __init__(self, df):
        self.df = df
    
    def execute(self, filters):
        """
        Filter the DataFrame based on provided filters
        
        Parameters:
        -----------
        filters : dict
            Dictionary of column names and filter conditions
            Example: {"gender": "Male", "age": ">50", "cholesterol": ">180"}
        
        Returns:
        --------
        list
            List of dictionaries containing matching records
        """
        filtered_df = self.df.copy()
        
        for column, condition in filters.items():
            if column in filtered_df.columns:
                # Handle different types of conditions
                if isinstance(condition, str) and condition.startswith(">"):
                    value = float(condition[1:])
                    filtered_df = filtered_df[filtered_df[column] > value]
                elif isinstance(condition, str) and condition.startswith("<"):
                    value = float(condition[1:])
                    filtered_df = filtered_df[filtered_df[column] < value]
                else:
                    # Handle exact match (case-insensitive for strings)
                    if filtered_df[column].dtype == 'object':
                        filtered_df = filtered_df[filtered_df[column].str.lower() == condition.lower()]
                    else:
                        filtered_df = filtered_df[filtered_df[column] == condition]
        
        # Convert filtered DataFrame to list of dictionaries
        return filtered_df.to_dict(orient='records')


class CheckMissingValues:
    """Tool to check for missing values in a specific column"""
    
    def __init__(self, df):
        self.df = df
    
    def execute(self, args):
        """
        Count missing values in the specified column
        
        Parameters:
        -----------
        args : dict
            Dictionary containing the column name
            Example: {"column": "cholesterol"}
        
        Returns:
        --------
        int
            Number of missing values in the column
        """
        column = args.get("column")
        
        if column in self.df.columns:
            return self.df[column].isna().sum()
        else:
            return f"Column '{column}' not found in the data"
