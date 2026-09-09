-- Synthetic demo only. Fresh UUIDs prevent links to production portraits.
-- Seed controls variations; UUIDs intentionally change on every rebuild.
SELECT setseed((abs(current_setting('year_end.demo_seed')::bigint % 2001) - 1000) / 1000.0);
DO $demo$
DECLARE
    people uuid[] := ARRAY[]::uuid[];
    person uuid;
    animal uuid;
    partnership uuid;
    folder uuid;
    review uuid;
    i integer;
    y integer;
    clip integer;
    first_names text[] := ARRAY['Rowan','Morgan','Alex','Jamie','Taylor','Casey','Robin','Avery','Quinn','Jordan','Sage','Reese'];
BEGIN
    FOR i IN 1..12 LOOP
        INSERT INTO public.persons
            (first_name,last_name,sex,birth_date,birth_date_precision)
        VALUES (first_names[i], CASE WHEN i <= 6 THEN 'Example' ELSE 'Sample' END,
                CASE WHEN i % 2 = 0 THEN 'f' ELSE 'm' END,
                make_date(CASE WHEN i <= 2 THEN 1950+i WHEN i <= 6 THEN 1974+i ELSE 1995+i END,
                          1+floor(random()*12)::integer, 1+floor(random()*28)::integer),'day')
        RETURNING person_id INTO person;
        people := array_append(people,person);
    END LOOP;
    INSERT INTO nello.founder(founder_id) VALUES (people[1]);
    -- Three couples and two generations of descendants; others remain unconnected.
    FOR i IN 1..3 LOOP
        INSERT INTO public.unions(union_date,union_date_precision,union_type,last_name_person_id)
        VALUES (make_date(CASE WHEN i=1 THEN 1973 ELSE 2000+i END,6,15),'day','marriage',people[2*i-1])
        RETURNING union_id INTO partnership;
        INSERT INTO public.union_members(person_id,union_id)
        VALUES (people[2*i-1],partnership),(people[2*i],partnership);
    END LOOP;
    INSERT INTO public.parents(child_id,parent_id,relation_type)
    SELECT people[c], people[p], 'biological' FROM generate_series(3,5,2) c CROSS JOIN generate_series(1,2) p;
    INSERT INTO public.parents(child_id,parent_id,relation_type)
    SELECT people[c], people[p], 'biological' FROM generate_series(7,9) c CROSS JOIN generate_series(3,4) p;
    INSERT INTO public.parents(child_id,parent_id,relation_type)
    SELECT people[10], people[p], 'adoptive' FROM generate_series(5,6) p;
    FOR i IN 1..3 LOOP
        INSERT INTO public.animals(first_name,species,sex,birth_date,birth_date_precision)
        VALUES ('Demo Pet '||i, CASE WHEN i=1 THEN 'cat' ELSE 'dog' END,'f',make_date(2010+i,4,12),'day')
        RETURNING animal_id INTO animal;
        INSERT INTO public.pets(pet_id,owner_id,relation_type,gotcha_date,gotcha_date_precision)
        VALUES (animal,people[i*2],'adoptive',make_date(2011+i,6,1),'day');
    END LOOP;
    FOR y IN 2017..2019 LOOP
        INSERT INTO publishing.reviews(review_type,project_year,video_theme,video_duration,video_resolution)
        VALUES ('year',y,'Demo annual review',600,'fhd') RETURNING review_id INTO review;
        FOR i IN 1..12 LOOP
            INSERT INTO project.folders(folder_name,project_year,person_id,media_type)
            VALUES ('Demo contributor '||i,y,people[i],'smartphone') RETURNING folder_id INTO folder;
            FOR clip IN 1..(1+floor(random()*4)::integer) LOOP
                INSERT INTO project.files(folder_id,file_name,file_size,video_duration,video_rating,
                                          video_resolution,video_date)
                VALUES (folder,'demo_clip_'||clip||'.mp4',10+floor(random()*50),20+floor(random()*80)::integer,
                        floor(random()*6)::integer,'fhd',make_date(y,7,15));
            END LOOP;
            INSERT INTO publishing.appearances(review_id,member_id,start_time,end_time)
            VALUES (review,people[i],(i-1)*30,(i-1)*30+10+floor(random()*15));
        END LOOP;
    END LOOP;
    INSERT INTO publishing.reviews(review_type,project_year,video_theme,video_duration,video_resolution)
    VALUES ('decade',2019,'Demo decade review',300,'fhd') RETURNING review_id INTO review;
    FOR i IN 1..10 LOOP
        INSERT INTO publishing.appearances(review_id,member_id,start_time,end_time)
        VALUES (review,people[i],(i-1)*20,(i-1)*20+15);
    END LOOP;
END
$demo$;
