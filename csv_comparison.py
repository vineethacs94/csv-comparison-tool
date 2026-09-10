import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

class CSVComparator:
    """Compare two CSV files and identify changes (added, updated, deleted records)"""
    
    def __init__(self, old_file, new_file, primary_key, output_file=None):
        """
        Initialize the comparator
        
        Args:
            old_file: Path to old CSV file
            new_file: Path to new CSV file
            primary_key: Primary key column name(s) for comparison (can be list for composite keys)
            output_file: Path to output CSV file (optional)
        """
        self.old_file = old_file
        self.new_file = new_file
        self.primary_key = primary_key if isinstance(primary_key, list) else [primary_key]
        self.output_file = output_file or f"comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        self.old_df = None
        self.new_df = None
        self.changes = {
            'added': [],
            'updated': [],
            'deleted': []
        }
    
    def print_progress(self, message):
        """Print progress message to terminal"""
        print(f"[*] {message}")
    
    def load_files(self):
        """Load CSV files"""
        try:
            self.print_progress(f"Loading old file: {self.old_file}")
            self.old_df = pd.read_csv(self.old_file)
            self.print_progress(f"  ✓ Loaded {len(self.old_df)} records from old file")
            
            self.print_progress(f"Loading new file: {self.new_file}")
            self.new_df = pd.read_csv(self.new_file)
            self.print_progress(f"  ✓ Loaded {len(self.new_df)} records from new file")
            
        except FileNotFoundError as e:
            print(f"[ERROR] File not found: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Error loading files: {e}")
            sys.exit(1)
    
    def validate_primary_keys(self):
        """Validate that primary key columns exist in both files"""
        for pk in self.primary_key:
            if pk not in self.old_df.columns:
                print(f"[ERROR] Primary key '{pk}' not found in old file")
                print(f"Available columns: {list(self.old_df.columns)}")
                sys.exit(1)
            if pk not in self.new_df.columns:
                print(f"[ERROR] Primary key '{pk}' not found in new file")
                print(f"Available columns: {list(self.new_df.columns)}")
                sys.exit(1)
        
        self.print_progress(f"✓ Primary keys validated: {self.primary_key}")
    
    def compare(self):
        """Compare old and new files to find changes"""
        self.print_progress("Starting comparison...")
        
        # Convert primary key columns to string for comparison
        old_df = self.old_df.copy()
        new_df = self.new_df.copy()
        
        for pk in self.primary_key:
            old_df[pk] = old_df[pk].astype(str).str.strip()
            new_df[pk] = new_df[pk].astype(str).str.strip()
        
        # Create composite key from multiple primary keys
        if len(self.primary_key) > 1:
            old_df['_composite_key'] = old_df[self.primary_key].apply(lambda x: '||'.join(x), axis=1)
            new_df['_composite_key'] = new_df[self.primary_key].apply(lambda x: '||'.join(x), axis=1)
            key_col = '_composite_key'
            self.print_progress(f"Using composite key: {' + '.join(self.primary_key)}")
        else:
            key_col = self.primary_key[0]
        
        old_keys = set(old_df[key_col])
        new_keys = set(new_df[key_col])
        
        self.print_progress(f"Old file unique keys: {len(old_keys)}")
        self.print_progress(f"New file unique keys: {len(new_keys)}")
        
        # 1. Find DELETED records (in old but not in new)
        deleted_keys = old_keys - new_keys
        if deleted_keys:
            self.print_progress(f"Found {len(deleted_keys)} deleted records")
            deleted_records = old_df[old_df[key_col].isin(deleted_keys)].copy()
            deleted_records['_change_type'] = 'DELETED'
            # Remove composite key column if it exists
            if '_composite_key' in deleted_records.columns:
                deleted_records = deleted_records.drop(columns=['_composite_key'])
            self.changes['deleted'] = deleted_records
        
        # 2. Find ADDED records (in new but not in old)
        added_keys = new_keys - old_keys
        if added_keys:
            self.print_progress(f"Found {len(added_keys)} newly added records")
            added_records = new_df[new_df[key_col].isin(added_keys)].copy()
            added_records['_change_type'] = 'ADDED'
            # Remove composite key column if it exists
            if '_composite_key' in added_records.columns:
                added_records = added_records.drop(columns=['_composite_key'])
            self.changes['added'] = added_records
        
        # 3. Find UPDATED records (in both, but with different values)
        common_keys = old_keys & new_keys
        if common_keys:
            self.print_progress(f"Comparing {len(common_keys)} common records for updates...")
            
            old_common = old_df[old_df[key_col].isin(common_keys)].reset_index(drop=True)
            new_common = new_df[new_df[key_col].isin(common_keys)].reset_index(drop=True)
            
            # Remove composite key column before comparison
            if '_composite_key' in old_common.columns:
                old_common = old_common.drop(columns=['_composite_key'])
            if '_composite_key' in new_common.columns:
                new_common = new_common.drop(columns=['_composite_key'])
            
            # Find rows that differ
            try:
                updated_records = []
                
                for i, new_row in new_common.iterrows():
                    # Find matching old row by primary key
                    mask = pd.Series([True] * len(old_common))
                    for pk in self.primary_key:
                        mask = mask & (old_common[pk].astype(str) == str(new_row[pk]))
                    
                    old_subset = old_common[mask]
                    
                    if len(old_subset) > 0:
                        old_row = old_subset.iloc[0]
                        # Check if any column value changed
                        if not old_row.equals(new_row):
                            record = new_row.copy()
                            record['_change_type'] = 'UPDATED'
                            updated_records.append(record)
                
                if updated_records:
                    self.print_progress(f"Found {len(updated_records)} updated records")
                    self.changes['updated'] = pd.DataFrame(updated_records)
            except Exception as e:
                self.print_progress(f"Warning: Error during update comparison: {e}")
        
        self.print_progress("✓ Comparison completed")
    
    def generate_report(self):
        """Generate comprehensive comparison report with all fields"""
        all_changes = []
        
        # Combine all changes
        for change_type, records in self.changes.items():
            if isinstance(records, pd.DataFrame) and len(records) > 0:
                all_changes.append(records)
        
        if all_changes:
            report_df = pd.concat(all_changes, ignore_index=True)
            
            # Reorder columns: put _change_type first, then primary keys, then all other columns
            cols = report_df.columns.tolist()
            if '_change_type' in cols:
                cols.remove('_change_type')
            
            # Remove primary keys from cols temporarily
            pk_cols = [pk for pk in self.primary_key if pk in cols]
            for pk in pk_cols:
                cols.remove(pk)
            
            # Reconstruct column order: _change_type, primary keys, then all other columns
            new_order = ['_change_type'] + pk_cols + cols
            report_df = report_df[[c for c in new_order if c in report_df.columns]]
            
            # Save to CSV
            try:
                report_df.to_csv(self.output_file, index=False)
                self.print_progress(f"✓ Report saved to: {self.output_file}")
            except Exception as e:
                print(f"[ERROR] Error saving report: {e}")
                sys.exit(1)
            
            return report_df
        else:
            self.print_progress("✓ No changes found between files")
            return pd.DataFrame()
    
    def print_summary(self):
        """Print summary statistics to terminal"""
        print("\n" + "="*70)
        print("COMPARISON SUMMARY")
        print("="*70)
        print(f"Old file: {self.old_file} ({len(self.old_df)} records)")
        print(f"New file: {self.new_file} ({len(self.new_df)} records)")
        print(f"Primary Keys: {', '.join(self.primary_key)}")
        print(f"\nChanges found:")
        print(f"  • Added:   {len(self.changes['added'])}")
        print(f"  • Updated: {len(self.changes['updated'])}")
        print(f"  • Deleted: {len(self.changes['deleted'])}")
        total_changes = len(self.changes['added']) + len(self.changes['updated']) + len(self.changes['deleted'])
        print(f"  • TOTAL:   {total_changes}")
        print(f"\nOutput file: {self.output_file}")
        print("="*70 + "\n")


def main():
    """Main function to run CSV comparison"""
    
    # Configuration - UPDATE THESE PATHS
    old_csv = "old_data.csv"
    new_csv = "new_data.csv"
    
    # PRIMARY KEYS - Using Account_vod__r.Id and Id (Address ID)
    primary_key = ["Account_vod__r.Id", "Id"]
    
    output_csv = "incremental_changes.csv"
    
    # Create comparator
    comparator = CSVComparator(old_csv, new_csv, primary_key, output_csv)
    
    # Run comparison
    comparator.load_files()
    comparator.validate_primary_keys()
    comparator.compare()
    comparator.generate_report()
    comparator.print_summary()


if __name__ == "__main__":
    main()
