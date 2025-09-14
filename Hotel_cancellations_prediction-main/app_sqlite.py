import streamlit as st
import numpy as np
import pickle
import sqlite3
import pandas as pd
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

def get_db_connection():
    """Get a connection to the SQLite database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row  # This enables accessing columns by name
        return conn
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return None

def fetch_booking_history():
    """Fetch booking history from the database"""
    try:
        conn = get_db_connection()
        if not conn:
            return []
            
        cursor = conn.cursor()
        query = """
            SELECT booking_id, arrival_date, arrival_month, room_type_reserved, 
                   no_of_adults, no_of_children, avg_price_per_room, 
                   cancellation_prediction, status
            FROM Bookings
            ORDER BY booking_id DESC
            LIMIT 10
        """
        cursor.execute(query)
        bookings = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return bookings
    except Exception as e:
        st.error(f"Error fetching booking history: {e}")
        return []

def main():
    st.title("Predicting Hotel Cancellations using Machine Learning")
    
    # Add tabs to the app
    tab1, tab2 = st.tabs(["New Booking", "Booking History"])
    
    with tab1:
        st.header("Enter Booking Details")
        # Booking input fields
        no_of_adults = st.number_input('Number of adults', step=1, min_value=1, value=1)
        no_of_children = st.number_input('Number of children', step=1, min_value=0, value=0)
        no_of_weekend_nights = st.number_input('Number of weekend nights', step=1, min_value=0, value=0)
        no_of_week_nights = st.number_input('Number of week nights', step=1, min_value=0, value=0)
        type_of_meal_plan = st.selectbox('Type of meal plan', ['Meal Plan 1', 'Meal Plan 2', 'Meal Plan 3', 'Not Selected'])
        required_car_parking_space = st.selectbox('Car parking space required', ['No', 'Yes'])
        room_type_reserved = st.selectbox('Room type reserved', ['Room Type 1', 'Room Type 2', 'Room Type 3', 'Room Type 4', 'Room Type 5', 'Room Type 6', 'Room Type 7'])
        lead_time = st.number_input('Lead time (days before arrival)', step=1, min_value=0, value=0)
        arrival_year = st.number_input('Year of arrival', step=1, min_value=2017, value=2023)
        arrival_month = st.slider('Month of arrival', step=1, min_value=1, max_value=12, value=datetime.now().month)
        arrival_date = st.slider('Date of arrival', step=1, min_value=1, max_value=31, value=min(datetime.now().day, 28))
        market_segment_type = st.selectbox('Market segment type', ['Aviation', 'Complementary', 'Corporate', 'Offline', 'Online'])
        repeated_guest = st.selectbox('Repeated guest', ['No', 'Yes'])
        no_of_previous_cancellations = st.number_input('Number of previous cancellations', step=1, min_value=0, value=0)
        no_of_previous_bookings_not_cancelled = st.number_input('Number of previous bookings not cancelled', step=1, min_value=0, value=0)
        avg_price_per_room = st.number_input('Average price per room', min_value=0.0, value=100.0)
        no_of_special_requests = st.number_input('Number of special requests', step=1, min_value=0, value=0)
        no_of_individuals = no_of_adults + no_of_children
        no_of_days_booked = no_of_weekend_nights + no_of_week_nights

        # Prepare input for model
        user_input = [
            no_of_adults,
            no_of_children,
            no_of_weekend_nights,
            no_of_week_nights,
            ['Meal Plan 1', 'Meal Plan 2', 'Meal Plan 3', 'Not Selected'].index(type_of_meal_plan),
            1 if required_car_parking_space == 'Yes' else 0,
            ['Room Type 1', 'Room Type 2', 'Room Type 3', 'Room Type 4', 'Room Type 5', 'Room Type 6', 'Room Type 7'].index(room_type_reserved),
            lead_time,
            arrival_year,
            arrival_month,
            arrival_date,
            ['Aviation', 'Complementary', 'Corporate', 'Offline', 'Online'].index(market_segment_type),
            1 if repeated_guest == 'Yes' else 0,
            no_of_previous_cancellations,
            no_of_previous_bookings_not_cancelled,
            avg_price_per_room,
            no_of_special_requests,
            no_of_individuals,
            no_of_days_booked
        ]

        if st.button('Predict'):
            # Check if model is loaded
            if model is None or scaler is None:
                st.error("Model not loaded correctly. Please check the model files.")
                cancel_prob = 0.5  # Default probability
                will_cancel = False
            else:
                try:
                    # Make prediction
                    scaled_data = scaler.transform(np.array([user_input]))
                    prediction = model.predict(scaled_data)
                    will_cancel = prediction[0] == 0  # 0 means canceled, 1 means not canceled
                    
                    # Get probability (optional, if model supports predict_proba)
                    try:
                        probs = model.predict_proba(scaled_data)[0]
                        cancel_prob = probs[0] if will_cancel else 1 - probs[1]
                    except:
                        cancel_prob = 0.7 if will_cancel else 0.3
                except Exception as e:
                    st.error(f"Prediction error: {e}")
                    cancel_prob = 0.5
                    will_cancel = False
            
            # Display result
            if will_cancel:
                st.error(f"Prediction: The booking will likely be canceled (Probability: {cancel_prob:.2f})")
            else:
                st.success(f"Prediction: The booking will likely be fulfilled (Probability: {1-cancel_prob:.2f})")

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
                        1,  # Default user_id
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
                    
                    conn.commit()
                    st.info("Booking saved to database.")
                    conn.close()
            except Exception as e:
                st.error(f"Failed to save booking: {e}")
    
    with tab2:
        st.header("Recent Booking History")
        bookings = fetch_booking_history()
        
        if bookings:
            st.write(f"Displaying {len(bookings)} recent bookings:")
            
            # Create a DataFrame for better display
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
            
            # Add risk level column
            if 'cancellation_prediction' in df.columns:
                df['risk_level'] = df['cancellation_prediction'].apply(get_risk_level)
            
            # Format dates
            if 'arrival_date' in df.columns:
                df['arrival_date'] = pd.to_datetime(df['arrival_date']).dt.date
            
            # Display the booking history
            st.dataframe(df)
        else:
            st.info("No booking history found.")

# Run the app
if __name__ == "__main__":
    main()