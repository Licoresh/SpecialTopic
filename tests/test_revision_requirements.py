import pandas as pd
from src.analytics import psf_demand_tables, skill_chart_tables
from src.cleaning import duplicate_ids
from src.utils import frame_hash


def test_framework_order_roles_and_unique_ad_denominators():
    jobs = pd.DataFrame({'source_id':['A','B','C'], 'job_family':['analytics','analytics','engineering']})
    mapping = pd.DataFrame({'source_id':['A','A','B','C'], 'psf_competency':['zeta','zeta','alpha','alpha'],
                            'psf_job_role':['analyst; scientist']*2+['analyst','engineer'],
                            'status':['ALIGNED','ALIGNED','PARTIALLY ALIGNED','NOT MAPPED']})
    taxonomy = pd.DataFrame({'competency_name':['zeta','alpha'], 'competency_id':['Z','A']})
    tables = psf_demand_tables(mapping, jobs, taxonomy)
    demand = tables['psf_chart_demand'].set_index('psf_competency')
    assert demand.loc['zeta','framework_order'] == 0 and demand.loc['alpha','framework_order'] == 1
    assert demand.job_ads.to_dict() == {'alpha':1,'zeta':1}
    assert abs(demand.loc['zeta','job_ads_pct'] - 100/3) < .001
    role_counts = tables['psf_role_family_demand'].set_index('psf_job_role').job_ads.to_dict()
    assert role_counts == {'analyst':2,'scientist':1}
    role_competency = tables['psf_role_competency_demand'].set_index(['psf_job_role','psf_competency']).job_ads.to_dict()
    assert role_competency == {('analyst','alpha'):1,('analyst','zeta'):1,('scientist','zeta'):1}
    scoped = psf_demand_tables(mapping.iloc[:3], jobs, taxonomy, denominator=2)
    assert scoped['psf_chart_demand'].set_index('psf_competency').job_ads_pct.to_dict() == {'alpha':50.0,'zeta':50.0}


def test_brand_aliases_count_once_without_merging_distinct_tools():
    jobs = pd.DataFrame({'source_id':['A','B']})
    skills = pd.DataFrame({'source_id':['A','A','B','B'], 'normalized_phrase':['powerbi','Power BI','Python','R']})
    demand = skill_chart_tables(skills,jobs)['chart_skill_demand'].set_index('employer_skill')
    assert demand.employer_demand_count.to_dict() == {'power bi':1,'python':1,'r':1}


def test_identical_reposting_flags_preserve_changed_content():
    jobs = pd.DataFrame({'source_id':['A','B','C'], 'job_title':['Analyst']*3,'company':['Acme']*3,
                         'location':['Cebu']*3,'job_description':['SQL Python','SQL Python','SQL R'],
                         'url':['https://example.test/'+x for x in 'ABC']})
    before = frame_hash(jobs)
    assert duplicate_ids(jobs) == ['B']
    assert frame_hash(jobs) == before


def test_screening_keeps_mapped_fingerprint_and_archived_records(workspace,jobs):
    from src import storage
    from streamlit.testing.v1 import AppTest
    storage.save_frame('mapped_jobs',jobs)
    stored_before = storage.read_frame('mapped_jobs')
    excluded = jobs.source_id.iloc[0]
    storage.save_json('cleaning_jobs',{'screening_exclusions':{excluded:'outside the selected occupation scope'}})
    app = AppTest.from_string('from src.ui import quality\nquality()').run(timeout=30)
    assert not app.exception
    quality_view = app.dataframe[0].value
    assert quality_view.columns.tolist() == ["Quality check", "Count"]
    assert "Missing: job description" in quality_view["Quality check"].tolist()
    next(item for item in app.checkbox if 'Philippine provenance' in item.label).check().run(timeout=30)
    next(item for item in app.button if item.label == 'Save cleaned dataset').click().run(timeout=30)
    assert not app.exception and not app.error
    assert excluded not in storage.read_frame('cleaned_jobs').source_id.tolist()
    assert storage.read_json('cleaning_jobs')['source_hash'] == frame_hash(jobs)
    pd.testing.assert_frame_equal(storage.read_frame('mapped_jobs'),stored_before)
