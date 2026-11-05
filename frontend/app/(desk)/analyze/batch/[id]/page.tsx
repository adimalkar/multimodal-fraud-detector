import BatchReport from "@/components/report/BatchReport";

const BatchPage = ({ params }: { params: { id: string } }) => <BatchReport id={params.id} />;

export default BatchPage;
