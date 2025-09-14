import streamlit as st
import numpy as np
import pickle
import sqlite3
import pandas as pd
import hashlib
from datetime import date, datetime

# Load the model and scaler
try:
    model = pickle.load(open("model.pkl", 'rb'))
    scaler = pickle.load(open("scaler.pkl", 'rb'))
except Exception as e:
    st.error(f"Error loading model: {e}")
    model = None
    scaler = None

# Database file path
DB_FILE = 'hotel_bookings.db'

# Authentication functions
def hash_password(password):
    """Create a SHA-256 hash of the password"""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate(email, password):
    """Authenticate user against the database"""
    try:
        conn = get_db_connection()
        if not conn:
            st.error("Database connection failed during authentication")
            return None
            
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            # For security, don't show specific error that email doesn't exist
            return None
            
        if user:
            stored_pw = user['password_hash']
            hashed_input = hash_password(password)
            
            # Check if password is stored as plain text (from setup script)
            if stored_pw == password:
                return dict(user)
            # Check if password matches the hash
            elif stored_pw == hashed_input:
                return dict(user)
            
            # Password didn't match but we found the user
            # For security, don't show specific error about password mismatch
            return None
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return None

def get_db_connection():
    """Get a connection to the SQLite database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row  # This enables accessing columns by name
        return conn
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return None

def fetch_booking_history(user_id=None):
    """Fetch booking history from the database. If user_id is provided, fetch only that user's bookings."""
    try:
        conn = get_db_connection()
        if not conn:
            return []
            
        cursor = conn.cursor()
        if user_id:
            # User view - only their own bookings
            query = """
                SELECT b.booking_id, b.arrival_date, b.arrival_month, b.room_type_reserved, 
                       b.no_of_adults, b.no_of_children, b.avg_price_per_room, 
                       b.status, r.room_type
                FROM Bookings b
                JOIN Rooms r ON b.room_id = r.room_id
                WHERE b.user_id = ?
                ORDER BY b.booking_id DESC
            """
            cursor.execute(query, (user_id,))
        else:
            # Admin view - all bookings with predictions
            query = """
                SELECT b.booking_id, b.arrival_date, b.arrival_month, b.room_type_reserved, 
                       b.no_of_adults, b.no_of_children, b.avg_price_per_room,
                       b.cancellation_prediction, b.status, 
                       u.email as user_email, u.full_name as user_name
                FROM Bookings b
                JOIN Users u ON b.user_id = u.user_id
                ORDER BY b.booking_id DESC
            """
            cursor.execute(query)
            
        bookings = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return bookings
    except Exception as e:
        st.error(f"Error fetching booking history: {e}")
        return []

def admin_dashboard():
    """Admin dashboard with all bookings and analytics"""
    st.header("Admin Dashboard")
    
    # Add tabs for different admin views
    admin_tabs = st.tabs(["All Bookings", "Analytics", "User Management"])
    
    with admin_tabs[0]:
        st.subheader("All Bookings")
        bookings = fetch_booking_history()  # No user_id means fetch all bookings
        
        if bookings:
            # Create DataFrame for display
            df = pd.DataFrame(bookings)
            
            # Convert prediction to risk level
            def get_risk_level(prob):
                if prob is None:
                    return "Unknown"
                try:
                    prob = float(prob)
                    if prob >= 0.7:
                        return "High"
                    elif prob >= 0.4:
                        return "Medium"
                    else:
                        return "Low"
                except:
                    return "Unknown"
            
            # Add risk level column if prediction exists
            if 'cancellation_prediction' in df.columns:
                df['risk_level'] = df['cancellation_prediction'].apply(get_risk_level)
                
                # Sort by risk level for better visibility
                risk_order = {"High": 0, "Medium": 1, "Low": 2, "Unknown": 3}
                df['risk_order'] = df['risk_level'].map(risk_order)
                df = df.sort_values('risk_order').drop('risk_order', axis=1)
            
            # Format dates
            if 'arrival_date' in df.columns:
                df['arrival_date'] = pd.to_datetime(df['arrival_date']).dt.date
                
            # Display the booking history with filters
            st.write(f"Total bookings: {len(df)}")
            
            # Filter options
            col1, col2, col3 = st.columns(3)
            with col1:
                if 'status' in df.columns:
                    status_filter = st.multiselect("Filter by Status", 
                                                options=sorted(df['status'].unique()),
                                                default=sorted(df['status'].unique()))
            with col2:
                if 'risk_level' in df.columns:
                    risk_filter = st.multiselect("Filter by Risk Level", 
                                               options=["High", "Medium", "Low", "Unknown"],
                                               default=["High", "Medium", "Low", "Unknown"])
            with col3:
                if 'room_type_reserved' in df.columns:
                    room_filter = st.multiselect("Filter by Room Type", 
                                               options=sorted(df['room_type_reserved'].unique()),
                                               default=sorted(df['room_type_reserved'].unique()))
            
            # Apply filters
            filtered_df = df.copy()
            if 'status' in df.columns and status_filter:
                filtered_df = filtered_df[filtered_df['status'].isin(status_filter)]
            if 'risk_level' in df.columns and risk_filter:
                filtered_df = filtered_df[filtered_df['risk_level'].isin(risk_filter)]
            if 'room_type_reserved' in df.columns and room_filter:
                filtered_df = filtered_df[filtered_df['room_type_reserved'].isin(room_filter)]
                
            # Show filtered data
            st.dataframe(filtered_df)
            
            # Export option
            if st.button("Export to CSV"):
                csv = filtered_df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"hotel_bookings_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        else:
            st.info("No booking history found.")
    
    with admin_tabs[1]:
        st.subheader("Analytics")
        
        # Get all bookings for analytics
        try:
            conn = get_db_connection()
            if conn:
                # Count bookings by status
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT status, COUNT(*) as count 
                    FROM Bookings 
                    GROUP BY status
                """)
                status_counts = {row['status']: row['count'] for row in cursor.fetchall()}
                
                # High risk bookings count
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM Bookings 
                    WHERE cancellation_prediction >= 0.7 AND status = 'Active'
                """)
                high_risk_count = cursor.fetchone()['count']
                
                # Room type distribution
                cursor.execute("""
                    SELECT room_type_reserved, COUNT(*) as count 
                    FROM Bookings 
                    GROUP BY room_type_reserved
                """)
                room_distribution = {row['room_type_reserved']: row['count'] for row in cursor.fetchall()}
                
                # Monthly booking trends
                cursor.execute("""
                    SELECT arrival_month, COUNT(*) as count 
                    FROM Bookings 
                    GROUP BY arrival_month
                    ORDER BY arrival_month
                """)
                monthly_trends = {row['arrival_month']: row['count'] for row in cursor.fetchall()}
                
                conn.close()
                
                # Display analytics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Bookings", sum(status_counts.values()))
                with col2:
                    active_count = status_counts.get('Active', 0)
                    st.metric("Active Bookings", active_count)
                with col3:
                    st.metric("High Risk Bookings", high_risk_count, 
                             f"{high_risk_count/active_count*100:.1f}% of active" if active_count else "0%")
                
                # Status distribution chart
                st.subheader("Booking Status Distribution")
                status_df = pd.DataFrame({
                    'Status': list(status_counts.keys()),
                    'Count': list(status_counts.values())
                })
                st.bar_chart(status_df.set_index('Status'))
                
                # Room type distribution chart
                st.subheader("Room Type Distribution")
                room_df = pd.DataFrame({
                    'Room Type': list(room_distribution.keys()),
                    'Count': list(room_distribution.values())
                })
                st.bar_chart(room_df.set_index('Room Type'))
                
                # Monthly trends chart
                st.subheader("Monthly Booking Trends")
                month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                month_df = pd.DataFrame({
                    'Month': [month_names[i-1] for i in monthly_trends.keys()],
                    'Count': list(monthly_trends.values()),
                    'Month_Num': list(monthly_trends.keys())
                }).sort_values('Month_Num')
                st.line_chart(month_df.set_index('Month')['Count'])
                
            else:
                st.error("Could not connect to the database for analytics")
        except Exception as e:
            st.error(f"Error loading analytics: {e}")
    
    with admin_tabs[2]:
        st.subheader("User Management")
        
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, email, full_name, role, created_at FROM Users")
                users = [dict(row) for row in cursor.fetchall()]
                conn.close()
                
                if users:
                    users_df = pd.DataFrame(users)
                    if 'created_at' in users_df.columns:
                        users_df['created_at'] = pd.to_datetime(users_df['created_at'])
                    st.dataframe(users_df)
                    
                    # Add new user form
                    st.subheader("Add New User")
                    with st.form("add_user_form"):
                        new_email = st.text_input("Email")
                        new_password = st.text_input("Password", type="password")
                        new_name = st.text_input("Full Name")
                        new_role = st.selectbox("Role", ["USER", "ADMIN"])
                        
                        submit = st.form_submit_button("Add User")
                        if submit and new_email and new_password:
                            try:
                                # Hash the password
                                hashed_pw = hash_password(new_password)
                                
                                # Insert new user
                                conn = get_db_connection()
                                if conn:
                                    cursor = conn.cursor()
                                    cursor.execute("""
                                        INSERT INTO Users (email, password_hash, full_name, role)
                                        VALUES (?, ?, ?, ?)
                                    """, (new_email, hashed_pw, new_name, new_role))
                                    conn.commit()
                                    conn.close()
                                    st.success(f"User {new_email} added successfully!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Error adding user: {e}")
                else:
                    st.info("No users found.")
        except Exception as e:
            st.error(f"Error loading users: {e}")

def user_interface(user):
    """Regular user interface for making bookings and viewing history"""
    st.header(f"Welcome, {user.get('full_name', 'User')}")
    
    # Add tabs for user views
    user_tabs = st.tabs(["Make a Booking", "My Bookings", "Account"])
    
    with user_tabs[0]:
        st.subheader("Book a Hotel Room")
        # Booking input fields
        no_of_adults = st.number_input('Number of adults', step=1, min_value=1, value=1)
        no_of_children = st.number_input('Number of children', step=1, min_value=0, value=0)
        no_of_weekend_nights = st.number_input('Number of weekend nights', step=1, min_value=0, value=0)
        no_of_week_nights = st.number_input('Number of week nights', step=1, min_value=0, value=0)
        type_of_meal_plan = st.selectbox('Type of meal plan', ['Meal Plan 1', 'Meal Plan 2', 'Meal Plan 3', 'Not Selected'])
        required_car_parking_space = st.selectbox('Car parking space required', ['No', 'Yes'])
        
        # Get available room types from database
        conn = get_db_connection()
        room_types = ['Room Type 1', 'Room Type 2', 'Room Type 3', 'Room Type 4', 'Room Type 5']
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT room_type FROM Rooms WHERE available_rooms > 0")
            room_types = [row['room_type'] for row in cursor.fetchall()]
            conn.close()
        
        room_type_reserved = st.selectbox('Room type', room_types)
        lead_time = st.number_input('Lead time (days before arrival)', step=1, min_value=0, value=0)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            arrival_year = st.number_input('Year of arrival', step=1, min_value=2023, value=datetime.now().year)
        with col2:
            arrival_month = st.slider('Month of arrival', step=1, min_value=1, max_value=12, value=datetime.now().month)
        with col3:
            arrival_date = st.slider('Date of arrival', step=1, min_value=1, max_value=31, value=min(datetime.now().day, 28))
        
        market_segment_type = st.selectbox('Market segment type', ['Online', 'Offline', 'Corporate', 'Complementary', 'Aviation'])
        repeated_guest = 'Yes' if user.get('user_id') in [1, 2] else 'No'  # Default users are considered repeat guests
        
        # Get user's previous booking info
        no_of_previous_cancellations = 0
        no_of_previous_bookings_not_cancelled = 0
        
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) as count FROM Bookings 
                    WHERE user_id = ? AND status = 'Cancelled'
                """, (user['user_id'],))
                no_of_previous_cancellations = cursor.fetchone()['count']
                
                cursor.execute("""
                    SELECT COUNT(*) as count FROM Bookings 
                    WHERE user_id = ? AND status = 'Completed'
                """, (user['user_id'],))
                no_of_previous_bookings_not_cancelled = cursor.fetchone()['count']
                
                conn.close()
        except:
            pass
        
        # Get room price
        avg_price_per_room = 100.0  # Default price
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT price FROM Rooms WHERE room_type = ?", (room_type_reserved,))
                result = cursor.fetchone()
                if result:
                    avg_price_per_room = result['price']
                conn.close()
        except:
            pass
        
        st.write(f"Room price per night: ${avg_price_per_room:.2f}")
        total_nights = no_of_weekend_nights + no_of_week_nights
        total_price = avg_price_per_room * total_nights
        st.write(f"Total for {total_nights} nights: ${total_price:.2f}")
        
        no_of_special_requests = st.number_input('Number of special requests', step=1, min_value=0, value=0)
        no_of_individuals = no_of_adults + no_of_children
        no_of_days_booked = no_of_weekend_nights + no_of_week_nights

        # Prepare input for model
        # Define valid room types for the model
        valid_room_types = ['Room Type 1', 'Room Type 2', 'Room Type 3', 'Room Type 4', 'Room Type 5', 'Room Type 6', 'Room Type 7']
        # Handle room type - if not in valid room types, use closest match
        if room_type_reserved not in valid_room_types:
            room_index = 0  # Default to first room type
        else:
            room_index = valid_room_types.index(room_type_reserved)
        
        # Valid market segment types
        market_segments = ['Aviation', 'Complementary', 'Corporate', 'Offline', 'Online']
        if market_segment_type not in market_segments:
            market_index = 4  # Default to Online
        else:
            market_index = market_segments.index(market_segment_type)
            
        # Valid meal plans
        meal_plans = ['Meal Plan 1', 'Meal Plan 2', 'Meal Plan 3', 'Not Selected']
        if type_of_meal_plan not in meal_plans:
            meal_index = 3  # Default to Not Selected
        else:
            meal_index = meal_plans.index(type_of_meal_plan)
            
        user_input = [
            no_of_adults,
            no_of_children,
            no_of_weekend_nights,
            no_of_week_nights,
            meal_index,
            1 if required_car_parking_space == 'Yes' else 0,
            room_index,
            lead_time,
            arrival_year,
            arrival_month,
            arrival_date,
            market_index,
            1 if repeated_guest == 'Yes' else 0,
            no_of_previous_cancellations,
            no_of_previous_bookings_not_cancelled,
            avg_price_per_room,
            no_of_special_requests,
            no_of_individuals,
            no_of_days_booked
        ]

        # Book button
        if st.button('Book Now'):
            # Get prediction silently - users don't see this
            cancel_prob = 0.3  # Default probability
            if model is not None and scaler is not None:
                try:
                    scaled_data = scaler.transform(np.array([user_input]))
                    prediction = model.predict(scaled_data)
                    will_cancel = prediction[0] == 0  # 0 means canceled, 1 means not canceled
                    
                    # Get probability
                    try:
                        probs = model.predict_proba(scaled_data)[0]
                        cancel_prob = probs[0] if will_cancel else 1 - probs[1]
                    except:
                        cancel_prob = 0.7 if will_cancel else 0.3
                except:
                    pass
            
            # Save to database
            try:
                conn = get_db_connection()
                if conn:
                    cursor = conn.cursor()
                    
                    # Get room_id based on room_type_reserved
                    room_id_query = "SELECT room_id FROM Rooms WHERE room_type = ? LIMIT 1"
                    cursor.execute(room_id_query, (room_type_reserved,))
                    room_result = cursor.fetchone()
                    room_id = room_result['room_id'] if room_result else 1
                    
                    # Insert booking
                    insert_query = """
                        INSERT INTO Bookings (
                            user_id, room_id, lead_time, market_segment_type, no_of_children, no_of_adults,
                            arrival_date, arrival_month, no_of_previous_cancellations, room_type_reserved,
                            no_of_week_nights, no_of_weekend_nights, repeated_guest, type_of_meal_plan,
                            no_of_special_requests, avg_price_per_room, cancellation_prediction, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    
                    # Format arrival date
                    try:
                        booking_date = date(arrival_year, arrival_month, arrival_date)
                    except ValueError:
                        st.warning("Invalid date. Using today's date instead.")
                        booking_date = date.today()
                    
                    # Execute insert
                    cursor.execute(insert_query, (
                        user['user_id'],
                        room_id,
                        lead_time,
                        market_segment_type,
                        no_of_children,
                        no_of_adults,
                        booking_date.isoformat(),
                        arrival_month,
                        no_of_previous_cancellations,
                        room_type_reserved,
                        no_of_week_nights,
                        no_of_weekend_nights,
                        1 if repeated_guest == 'Yes' else 0,
                        type_of_meal_plan,
                        no_of_special_requests,
                        avg_price_per_room,
                        float(cancel_prob),
                        'Active'
                    ))
                    
                    # Update available rooms
                    cursor.execute("""
                        UPDATE Rooms SET available_rooms = available_rooms - 1
                        WHERE room_id = ? AND available_rooms > 0
                    """, (room_id,))
                    
                    conn.commit()
                    st.success(f"Booking confirmed! Total cost: ${total_price:.2f}")
                    conn.close()
            except Exception as e:
                st.error(f"Failed to complete booking: {e}")
    
    with user_tabs[1]:
        st.subheader("My Bookings")
        user_bookings = fetch_booking_history(user['user_id'])
        
        if user_bookings:
            # Create DataFrame for display
            df = pd.DataFrame(user_bookings)
            
            # Format dates
            if 'arrival_date' in df.columns:
                df['arrival_date'] = pd.to_datetime(df['arrival_date']).dt.date
            
            # Sort by booking ID (descending)
            df = df.sort_values('booking_id', ascending=False)
            
            # Display bookings
            st.dataframe(df)
            
            # Option to cancel a booking
            st.subheader("Cancel a Booking")
            active_bookings = df[df['status'] == 'Active'] if 'status' in df.columns else df
            if not active_bookings.empty:
                booking_to_cancel = st.selectbox("Select booking to cancel", 
                                               options=active_bookings['booking_id'].tolist(),
                                               format_func=lambda x: f"Booking #{x} - {active_bookings[active_bookings['booking_id']==x]['room_type_reserved'].values[0]} on {active_bookings[active_bookings['booking_id']==x]['arrival_date'].values[0]}"
                                              )
                
                if st.button("Cancel Selected Booking"):
                    try:
                        conn = get_db_connection()
                        if conn:
                            cursor = conn.cursor()
                            
                            # Update booking status
                            cursor.execute("""
                                UPDATE Bookings SET status = 'Cancelled'
                                WHERE booking_id = ? AND user_id = ?
                            """, (booking_to_cancel, user['user_id']))
                            
                            # Get room_id to update available rooms
                            cursor.execute("SELECT room_id FROM Bookings WHERE booking_id = ?", (booking_to_cancel,))
                            room_id = cursor.fetchone()['room_id']
                            
                            # Update available rooms
                            cursor.execute("""
                                UPDATE Rooms SET available_rooms = available_rooms + 1
                                WHERE room_id = ?
                            """, (room_id,))
                            
                            # Add to history
                            cursor.execute("""
                                INSERT INTO History (user_id, booking_id)
                                VALUES (?, ?)
                            """, (user['user_id'], booking_to_cancel))
                            
                            conn.commit()
                            st.success("Booking cancelled successfully")
                            conn.close()
                            
                            # Refresh the page to show updated bookings
                            st.rerun()
                    except Exception as e:
                        st.error(f"Failed to cancel booking: {e}")
            else:
                st.info("You have no active bookings to cancel.")
        else:
            st.info("You haven't made any bookings yet.")
    
    with user_tabs[2]:
        st.subheader("Account Information")
        
        # Display user info
        st.write(f"**Email:** {user['email']}")
        st.write(f"**Name:** {user.get('full_name', 'Not provided')}")
        st.write(f"**Role:** {user['role']}")
        
        # Change password form
        st.subheader("Change Password")
        with st.form("change_password_form"):
            current_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            
            submit = st.form_submit_button("Update Password")
            if submit:
                if new_password != confirm_password:
                    st.error("New passwords don't match")
                elif not authenticate(user['email'], current_password):
                    st.error("Current password is incorrect")
                else:
                    try:
                        hashed_new_pw = hash_password(new_password)
                        conn = get_db_connection()
                        if conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE Users SET password_hash = ?
                                WHERE user_id = ?
                            """, (hashed_new_pw, user['user_id']))
                            conn.commit()
                            conn.close()
                            st.success("Password updated successfully!")
                    except Exception as e:
                        st.error(f"Failed to update password: {e}")

def login_page():
    """Display login form"""
    st.header("Login")
    
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        if email and password:
            user = authenticate(email, password)
            if user:
                st.session_state['user'] = user
                st.rerun()
            else:
                st.error("Invalid email or password")
        else:
            st.warning("Please enter both email and password")
    
    st.write("---")
    st.write("For testing:")
    st.write("- Admin: admin@example.com / admin123")
    st.write("- User: user@example.com / user123")
    
    # Registration option
    st.write("---")
    st.write("Don't have an account?")
    if st.button("Register New Account"):
        st.session_state['show_register'] = True
        st.rerun()
    
    # Registration form
    if st.session_state.get('show_register', False):
        st.subheader("Register")
        with st.form("registration_form"):
            new_email = st.text_input("Email Address")
            new_password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            full_name = st.text_input("Full Name")
            
            submit = st.form_submit_button("Create Account")
            if submit:
                if new_password != confirm_password:
                    st.error("Passwords don't match")
                elif not new_email or not new_password:
                    st.warning("Email and password are required")
                else:
                    try:
                        conn = get_db_connection()
                        if conn:
                            cursor = conn.cursor()
                            
                            # Check if email already exists
                            cursor.execute("SELECT COUNT(*) as count FROM Users WHERE email = ?", (new_email,))
                            if cursor.fetchone()['count'] > 0:
                                st.error("Email already registered")
                            else:
                                # Create new user
                                hashed_pw = hash_password(new_password)
                                cursor.execute("""
                                    INSERT INTO Users (email, password_hash, full_name, role)
                                    VALUES (?, ?, ?, 'USER')
                                """, (new_email, hashed_pw, full_name))
                                conn.commit()
                                st.success("Registration successful! You can now log in.")
                                st.session_state['show_register'] = False
                                conn.close()
                                # Refresh the page so user can login
                                st.rerun()
                    except Exception as e:
                        st.error(f"Registration error: {e}")

def main():
    st.title("Hotel Booking System")
    
    # Initialize session state
    if 'user' not in st.session_state:
        st.session_state['user'] = None
    
    if 'show_register' not in st.session_state:
        st.session_state['show_register'] = False
    
    # Logout button
    if st.session_state['user']:
        if st.sidebar.button("Logout"):
            st.session_state['user'] = None
            st.rerun()
    
    # Display appropriate interface based on login status and role
    if st.session_state['user']:
        user = st.session_state['user']
        if user['role'] == 'ADMIN':
            admin_dashboard()
        else:
            user_interface(user)
    else:
        login_page()

# Run the app
if __name__ == "__main__":
    main()