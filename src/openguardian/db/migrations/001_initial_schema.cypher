// Device Constraints
CREATE CONSTRAINT const_device_id IF NOT EXISTS FOR (d:Device) REQUIRE d.id IS UNIQUE;

// User Constraints
CREATE CONSTRAINT const_user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE;

// Activity Constraints
CREATE CONSTRAINT const_activity_name IF NOT EXISTS FOR (a:Activity) REQUIRE a.name IS UNIQUE;

// TimeSlot Constraints
CREATE CONSTRAINT const_timeslot_id IF NOT EXISTS FOR (t:TimeSlot) REQUIRE t.id IS UNIQUE;

// Schema tracking node constraint
CREATE CONSTRAINT const_migration_name IF NOT EXISTS FOR (m:Migration) REQUIRE m.name IS UNIQUE;
