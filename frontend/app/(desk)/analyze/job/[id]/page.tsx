import JobReport from "@/components/report/JobReport";

const JobPage = ({ params }: { params: { id: string } }) => <JobReport id={params.id} />;

export default JobPage;
